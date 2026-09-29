/* SD card in SPI mode: init (SDSC / SDHC), single-block read and write.
 * The SPI access goes through callbacks (host tests: sw/test/test_sd.c with a card model). */
#ifndef SD_H_INCLUDED
#define SD_H_INCLUDED

#include <stdint.h>

struct sd {
    uint8_t (*xfer)(void *ctx, uint8_t b);
    void (*select)(void *ctx, int on);   /* CS */
    void (*speed)(void *ctx, int fast);  /* 0: <= 400 kHz for init, 1: full speed */
    void *ctx;
    int sdhc;                            /* block addressing */
    int ready;
};

enum { SD_OK = 0, SD_ENOCARD = -1, SD_EINIT = -2, SD_ECMD = -3, SD_ETIMEOUT = -4, SD_EWRITE = -5 };

int sd_init(struct sd *s);
int sd_read(struct sd *s, uint32_t lba, uint8_t *buf);
int sd_write(struct sd *s, uint32_t lba, const uint8_t *buf);

#endif
