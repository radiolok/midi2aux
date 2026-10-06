/* FAT16 / FAT32 on a block device: files in the root directory, 8.3 names (long-name entries
 * are skipped), one sector cache. Enough for presets and a firmware image on an SD card.
 * Host tests: sw/test/test_fat.c against images from sw/tools/fatimg.py. */
#ifndef FAT_H_INCLUDED
#define FAT_H_INCLUDED

#include <stdint.h>

struct blkdev {
    int (*read)(void *ctx, uint32_t lba, uint8_t *buf);        /* 512-byte sectors, 0 = ok */
    int (*write)(void *ctx, uint32_t lba, const uint8_t *buf);
    void *ctx;
};

struct fat {
    struct blkdev dev;
    uint32_t fat0, fatsz, nfats, root0, root_secs, data0, spc, nclus, root_clus, eoc;
    int fat32;
    uint32_t buf_lba;
    int dirty;
    uint8_t buf[512];
};

struct fat_file {
    uint32_t first, clus, pos, size;
};

enum { FAT_OK = 0, FAT_EIO = -1, FAT_ENOFS = -2, FAT_ENOENT = -3, FAT_EFULL = -4, FAT_EBIG = -5 };

int fat_mount(struct fat *f, struct blkdev dev);
int fat_open(struct fat *f, const char *name, struct fat_file *file);
/* reads up to n bytes from the current position; returns the count or an error */
int32_t fat_fread(struct fat *f, struct fat_file *file, void *dst, uint32_t n);
/* whole file into dst (at most max bytes, else FAT_EBIG); returns its size or an error */
int32_t fat_read(struct fat *f, const char *name, void *dst, uint32_t max);
/* creates or replaces a root-directory file */
int fat_write(struct fat *f, const char *name, const void *src, uint32_t len);
/* calls cb for each file of the root directory (name as "NAME.EXT") */
int fat_list(struct fat *f, void (*cb)(void *ctx, const char *name, uint32_t size), void *ctx);
int fat_flush(struct fat *f);

#endif
