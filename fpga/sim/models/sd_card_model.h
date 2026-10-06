/* SD card in SPI mode, byte level (C and C++): CMD0/8/55/41/58/16/17/24, SDHC (block addresses)
 * or SDSC (byte addresses), a few 0xFF bytes before responses and data tokens, busy after writes.
 * Checks the CRC of CMD0 / CMD8 (required in SPI mode) and the command framing.
 * Used by sw/test/test_sd.c and the Verilator testbench (fpga/sim/tb/soc_models.h). */
#ifndef SD_CARD_MODEL_H
#define SD_CARD_MODEL_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>

struct sd_card {
    uint8_t *img;          /* card contents */
    size_t size;           /* bytes */
    int sdhc;              /* 1: block addressing (CCS) */
    int acmd41_busy;       /* ACMD41 answers "idle" this many times */
    int errors;            /* protocol errors seen */
    /* state */
    int idle, app, ready;
    uint8_t cmd[6];
    int ncmd;
    uint8_t out[600];      /* queued MISO bytes */
    int nout, pout;
    int wr_state;          /* 0 none, 1 wait token, 2 data, 3 crc */
    uint32_t wr_addr;
    int wr_n;
    uint8_t wr_buf[512];
    uint32_t reads, writes;
};

static inline void sd_card_init(struct sd_card *c, uint8_t *img, size_t size, int sdhc)
{
    memset(c, 0, sizeof *c);
    c->img = img;
    c->size = size;
    c->sdhc = sdhc;
    c->acmd41_busy = 3;
}

static inline void sd_q(struct sd_card *c, uint8_t b)
{
    if (c->nout < (int)sizeof c->out)
        c->out[c->nout++] = b;
}

static inline void sd_card_deselect(struct sd_card *c)
{
    c->ncmd = 0;
    c->nout = c->pout = 0;
    c->wr_state = 0;
}

static inline void sd_card_cmd(struct sd_card *c)
{
    uint8_t idx = c->cmd[0] & 0x3F;
    uint32_t arg = (uint32_t)c->cmd[1] << 24 | (uint32_t)c->cmd[2] << 16 | (uint32_t)c->cmd[3] << 8 | c->cmd[4];
    int app = c->app;
    uint8_t r1 = c->idle ? 0x01 : 0x00;
    c->app = 0;
    c->nout = c->pout = 0;
    sd_q(c, 0xFF); /* NCR */
    if ((c->cmd[0] & 0xC0) != 0x40) {
        c->errors++;
        return;
    }
    if (idx == 0) {
        if (c->cmd[5] != 0x95)
            c->errors++;
        c->idle = 1;
        c->ready = 0;
        sd_q(c, 0x01);
    } else if (idx == 8) {
        if (c->cmd[5] != 0x87)
            c->errors++;
        sd_q(c, r1);
        sd_q(c, 0);
        sd_q(c, 0);
        sd_q(c, (uint8_t)(arg >> 8 & 0x0F));
        sd_q(c, (uint8_t)arg);
    } else if (idx == 55) {
        c->app = 1;
        sd_q(c, r1);
    } else if (idx == 41 && app) {
        if (c->acmd41_busy > 0) {
            c->acmd41_busy--;
        } else if (!c->sdhc || (arg & 0x40000000u)) {
            c->idle = 0;
            c->ready = 1;
        }
        sd_q(c, c->idle ? 0x01 : 0x00);
    } else if (idx == 58) {
        sd_q(c, r1);
        sd_q(c, (uint8_t)(0x80 | (c->sdhc ? 0x40 : 0)) & (c->ready ? 0xFF : 0x3F));
        sd_q(c, 0xFF);
        sd_q(c, 0x80);
        sd_q(c, 0x00);
    } else if (idx == 16) {
        sd_q(c, arg == 512 ? r1 : (uint8_t)(r1 | 0x40));
    } else if ((idx == 17 || idx == 24) && c->ready) {
        uint32_t a = c->sdhc ? arg * 512u : arg;
        if (a % 512 || a + 512 > c->size) {
            sd_q(c, 0x20); /* address error */
            return;
        }
        sd_q(c, 0x00);
        if (idx == 17) {
            sd_q(c, 0xFF);
            sd_q(c, 0xFF);
            sd_q(c, 0xFE);
            for (int i = 0; i < 512; i++)
                sd_q(c, c->img[a + i]);
            sd_q(c, 0x12);
            sd_q(c, 0x34);
            c->reads++;
        } else {
            c->wr_state = 1;
            c->wr_addr = a;
        }
    } else {
        sd_q(c, (uint8_t)(r1 | 0x04)); /* illegal command */
    }
}

/* one byte exchanged while CS is low */
static inline uint8_t sd_card_xfer(struct sd_card *c, uint8_t in)
{
    uint8_t o = c->pout < c->nout ? c->out[c->pout++] : 0xFF;
    if (c->wr_state == 1) {
        if (c->pout >= c->nout && in == 0xFE) {
            c->wr_state = 2;
            c->wr_n = 0;
        }
        return o;
    }
    if (c->wr_state == 2) {
        c->wr_buf[c->wr_n++] = in;
        if (c->wr_n == 512)
            c->wr_state = 3, c->wr_n = 0;
        return 0xFF;
    }
    if (c->wr_state == 3) {
        if (++c->wr_n == 2) {
            memcpy(c->img + c->wr_addr, c->wr_buf, 512);
            c->writes++;
            c->wr_state = 0;
            c->nout = c->pout = 0;
            sd_q(c, 0x05); /* data accepted */
            for (int i = 0; i < 4; i++)
                sd_q(c, 0x00); /* busy */
        }
        return 0xFF;
    }
    if (c->ncmd == 0 && in == 0xFF)
        return o;
    if (c->ncmd == 0 && (in & 0xC0) != 0x40) {
        c->errors++;
        return o;
    }
    c->cmd[c->ncmd++] = in;
    if (c->ncmd == 6) {
        c->ncmd = 0;
        sd_card_cmd(c);
    }
    return o;
}

#endif
