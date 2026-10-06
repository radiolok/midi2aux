#include "storage.h"

#include "lib.h"
#include "preset.h"

static int blk_read(void *ctx, uint32_t lba, uint8_t *buf) { return sd_read(ctx, lba, buf); }
static int blk_write(void *ctx, uint32_t lba, const uint8_t *buf) { return sd_write(ctx, lba, buf); }

int storage_mount(struct storage *st, struct sd sd)
{
    st->sd = sd;
    st->mounted = 0;
    int r = sd_init(&st->sd);
    if (r)
        return r;
    r = fat_mount(&st->fat, (struct blkdev){blk_read, blk_write, &st->sd});
    st->mounted = r == FAT_OK;
    return r;
}

int storage_save(struct storage *st, const struct synth *s, int n)
{
    uint8_t buf[PRESET_MAX_BYTES];
    char name[13];
    if (!st->mounted)
        return SD_ENOCARD;
    preset_name(n, name);
    return fat_write(&st->fat, name, buf, (uint32_t)preset_pack(s, buf));
}

int storage_load(struct storage *st, struct synth *s, int n)
{
    uint8_t buf[PRESET_MAX_BYTES + 64];
    char name[13];
    if (!st->mounted)
        return SD_ENOCARD;
    preset_name(n, name);
    int32_t len = fat_read(&st->fat, name, buf, sizeof buf);
    if (len < 0)
        return (int)len;
    int r = preset_unpack(s, buf, (int)len);
    return r < 0 ? FAT_ENOFS : r;
}

int storage_list(struct storage *st, void (*cb)(void *ctx, const char *name, uint32_t size), void *ctx)
{
    return st->mounted ? fat_list(&st->fat, cb, ctx) : SD_ENOCARD;
}

int32_t storage_fw_update(struct storage *st, int spi, uint32_t offset, uint32_t max_len)
{
    struct fat_file f;
    uint8_t buf[256];
    uint32_t crc = 0;
    if (!st->mounted)
        return SD_ENOCARD;
    int r = fat_open(&st->fat, "FIRMWARE.BIN", &f);
    if (r)
        return r;
    if (!f.size || f.size > max_len)
        return -10;
    for (uint32_t a = 0; a < FW_HDR_SIZE + f.size; a += 4096)
        flash_erase_4k(spi, offset + a);
    for (uint32_t pos = 0; pos < f.size;) {
        int32_t k = fat_fread(&st->fat, &f, buf, sizeof buf);
        if (k <= 0)
            return FAT_EIO;
        flash_program(spi, offset + FW_HDR_SIZE + pos, buf, (size_t)k);
        crc = crc32_update(crc, buf, (size_t)k);
        pos += (uint32_t)k;
    }
    /* verify the flash copy before the header makes it bootable */
    uint32_t c = 0;
    for (uint32_t a = 0; a < f.size; a += sizeof buf) {
        uint32_t k = f.size - a < sizeof buf ? f.size - a : sizeof buf;
        flash_read(spi, offset + FW_HDR_SIZE + a, buf, k);
        c = crc32_update(c, buf, k);
    }
    if (c != crc)
        return -11;
    struct fw_header h = {FW_MAGIC, f.size, crc};
    flash_program(spi, offset, &h, sizeof h);
    return (int32_t)f.size;
}
