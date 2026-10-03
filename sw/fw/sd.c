#include "sd.h"

#define SD_POLL 20000u /* bytes to wait for a token / not busy (~10 ms at 16 MHz) */

static uint8_t cmd(struct sd *s, uint8_t idx, uint32_t arg, uint8_t crc)
{
    s->xfer(s->ctx, 0xFF);
    s->xfer(s->ctx, 0x40 | idx);
    s->xfer(s->ctx, (uint8_t)(arg >> 24));
    s->xfer(s->ctx, (uint8_t)(arg >> 16));
    s->xfer(s->ctx, (uint8_t)(arg >> 8));
    s->xfer(s->ctx, (uint8_t)arg);
    s->xfer(s->ctx, crc);
    for (int i = 0; i < 10; i++) { /* NCR: up to 8 bytes */
        uint8_t r = s->xfer(s->ctx, 0xFF);
        if (!(r & 0x80))
            return r;
    }
    return 0xFF;
}

static void deselect(struct sd *s)
{
    s->select(s->ctx, 0);
    s->xfer(s->ctx, 0xFF);
}

int sd_init(struct sd *s)
{
    uint8_t r = 0xFF;
    s->ready = 0;
    s->sdhc = 0;
    s->speed(s->ctx, 0);
    s->select(s->ctx, 0);
    for (int i = 0; i < 10; i++) /* >= 74 clocks with CS high */
        s->xfer(s->ctx, 0xFF);
    s->select(s->ctx, 1);
    for (int i = 0; i < 10 && r != 0x01; i++)
        r = cmd(s, 0, 0, 0x95);
    if (r != 0x01) {
        deselect(s);
        return SD_ENOCARD;
    }
    int v2 = 0;
    if (cmd(s, 8, 0x1AA, 0x87) == 0x01) {
        uint8_t b[4];
        for (int i = 0; i < 4; i++)
            b[i] = s->xfer(s->ctx, 0xFF);
        if ((b[2] & 0x0F) != 0x01 || b[3] != 0xAA) {
            deselect(s);
            return SD_EINIT;
        }
        v2 = 1;
    }
    for (uint32_t i = 0;; i++) {
        if (i == 5000u) {
            deselect(s);
            return SD_ETIMEOUT;
        }
        cmd(s, 55, 0, 0x65);
        r = cmd(s, 41, v2 ? 0x40000000u : 0, 0x77);
        if (r == 0x00)
            break;
        if (r != 0x01) {
            deselect(s);
            return SD_EINIT;
        }
    }
    if (v2 && cmd(s, 58, 0, 0xFD) == 0x00) {
        uint8_t ocr0 = s->xfer(s->ctx, 0xFF);
        for (int i = 0; i < 3; i++)
            s->xfer(s->ctx, 0xFF);
        s->sdhc = (ocr0 & 0x40) != 0;
    }
    if (!s->sdhc && cmd(s, 16, 512, 0x15) != 0x00) {
        deselect(s);
        return SD_EINIT;
    }
    deselect(s);
    s->speed(s->ctx, 1);
    s->ready = 1;
    return SD_OK;
}

int sd_read(struct sd *s, uint32_t lba, uint8_t *buf)
{
    if (!s->ready)
        return SD_ENOCARD;
    s->select(s->ctx, 1);
    if (cmd(s, 17, s->sdhc ? lba : lba * 512u, 0x01) != 0x00) {
        deselect(s);
        return SD_ECMD;
    }
    uint32_t i = 0;
    uint8_t t;
    while ((t = s->xfer(s->ctx, 0xFF)) == 0xFF && ++i < SD_POLL)
        ;
    if (t != 0xFE) {
        deselect(s);
        return SD_ETIMEOUT;
    }
    for (int k = 0; k < 512; k++)
        buf[k] = s->xfer(s->ctx, 0xFF);
    s->xfer(s->ctx, 0xFF); /* CRC */
    s->xfer(s->ctx, 0xFF);
    deselect(s);
    return SD_OK;
}

int sd_write(struct sd *s, uint32_t lba, const uint8_t *buf)
{
    if (!s->ready)
        return SD_ENOCARD;
    s->select(s->ctx, 1);
    if (cmd(s, 24, s->sdhc ? lba : lba * 512u, 0x01) != 0x00) {
        deselect(s);
        return SD_ECMD;
    }
    s->xfer(s->ctx, 0xFF);
    s->xfer(s->ctx, 0xFE);
    for (int k = 0; k < 512; k++)
        s->xfer(s->ctx, buf[k]);
    s->xfer(s->ctx, 0xFF); /* CRC (not checked in SPI mode) */
    s->xfer(s->ctx, 0xFF);
    uint8_t d = s->xfer(s->ctx, 0xFF);
    uint32_t i = 0;
    while (s->xfer(s->ctx, 0xFF) == 0x00 && ++i < SD_POLL * 10)
        ;
    deselect(s);
    if ((d & 0x1F) != 0x05)
        return SD_EWRITE;
    return i < SD_POLL * 10 ? SD_OK : SD_ETIMEOUT;
}
