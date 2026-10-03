/* SD card storage: presets and firmware update (FIRMWARE.BIN -> SPI flash, format of the boot
 * loader: header {"AVKF", len, crc} + image at +256). */
#ifndef STORAGE_H_INCLUDED
#define STORAGE_H_INCLUDED

#include "fat.h"
#include "sd.h"
#include "synth.h"

struct storage {
    struct sd sd;
    struct fat fat;
    int mounted;
};

int storage_mount(struct storage *st, struct sd sd);          /* 0 or an SD_* / FAT_* error */
int storage_save(struct storage *st, const struct synth *s, int n);
int storage_load(struct storage *st, struct synth *s, int n);  /* values used, or an error */
int storage_list(struct storage *st, void (*cb)(void *ctx, const char *name, uint32_t size), void *ctx);
/* copies FIRMWARE.BIN to flash (spi, offset); returns its length or an error (-10: too big,
 * -11: verify) */
int32_t storage_fw_update(struct storage *st, int spi, uint32_t offset, uint32_t max_len);

#endif
