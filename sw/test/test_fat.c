/* fat.c on FAT16 / FAT32 images made by tools/fatimg.py (fragmented files, long-name entries).
 * Usage: test_fat DIR -- reads DIR/fat16.img, DIR/fat32.img, DIR/big.bin; writes DIR/out16.img,
 * DIR/out32.img, which the Makefile checks again with fatimg.py. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "unity_lite.h"

#include "../fw/fat.c"

struct img {
    uint8_t *d;
    size_t n;
    int reads, writes;
};

static int img_read(void *ctx, uint32_t lba, uint8_t *buf)
{
    struct img *m = ctx;
    if ((size_t)(lba + 1) * 512 > m->n)
        return -1;
    memcpy(buf, m->d + (size_t)lba * 512, 512);
    m->reads++;
    return 0;
}

static int img_write(void *ctx, uint32_t lba, const uint8_t *buf)
{
    struct img *m = ctx;
    if ((size_t)(lba + 1) * 512 > m->n)
        return -1;
    memcpy(m->d + (size_t)lba * 512, buf, 512);
    m->writes++;
    return 0;
}

static uint8_t *load(const char *path, size_t *n)
{
    FILE *fp = fopen(path, "rb");
    if (!fp)
        return 0;
    fseek(fp, 0, SEEK_END);
    *n = (size_t)ftell(fp);
    fseek(fp, 0, SEEK_SET);
    uint8_t *d = malloc(*n);
    if (fread(d, 1, *n, fp) != *n)
        *n = 0;
    fclose(fp);
    return d;
}

static const char *dir;
static uint8_t big[4096];
static size_t big_n;

static void list_cb(void *ctx, const char *name, uint32_t size)
{
    char *s = ctx;
    char line[40];
    snprintf(line, sizeof line, "%s:%u ", name, size);
    strcat(s, line);
}

static void run(int bits)
{
    char path[512];
    snprintf(path, sizeof path, "%s/fat%d.img", dir, bits);
    struct img m = {0};
    m.d = load(path, &m.n);
    CHECK(m.d != 0);
    if (!m.d)
        return;
    struct fat f;
    CHECK_EQ(fat_mount(&f, (struct blkdev){img_read, img_write, &m}), FAT_OK);
    CHECK_EQ(f.fat32, bits == 32);
    static uint8_t buf[8192];
    CHECK_EQ(fat_read(&f, "big.bin", buf, sizeof buf), (int32_t)big_n);
    CHECK(!memcmp(buf, big, big_n));
    CHECK_EQ(fat_read(&f, "HELLO.TXT", buf, sizeof buf), 6);
    CHECK(!memcmp(buf, "hello\n", 6));
    CHECK_EQ(fat_read(&f, "NONE.TXT", buf, sizeof buf), FAT_ENOENT);
    CHECK_EQ(fat_read(&f, "BIG.BIN", buf, 100), FAT_EBIG);
    /* streaming read in odd-sized pieces */
    struct fat_file ff;
    CHECK_EQ(fat_open(&f, "BIG.BIN", &ff), FAT_OK);
    size_t got = 0;
    int32_t k;
    while ((k = fat_fread(&f, &ff, buf + got, 77)) > 0)
        got += (size_t)k;
    CHECK_EQ(got, big_n);
    CHECK(!memcmp(buf, big, big_n));
    char names[256] = "";
    CHECK_EQ(fat_list(&f, list_cb, names), FAT_OK);
    CHECK_STR(names, "BIG.BIN:3000 HELLO.TXT:6 ");
    /* writes: a new file, a bigger and a smaller replacement, an empty file */
    for (int i = 0; i < 5000; i++)
        buf[i] = (uint8_t)(i * 7 + bits);
    CHECK_EQ(fat_write(&f, "new.txt", buf, 5000), FAT_OK);
    CHECK_EQ(fat_write(&f, "HELLO.TXT", buf + 100, 1500), FAT_OK);
    CHECK_EQ(fat_write(&f, "BIG.BIN", "small", 5), FAT_OK);
    CHECK_EQ(fat_write(&f, "EMPTY", "", 0), FAT_OK);
    static uint8_t rb[8192];
    CHECK_EQ(fat_read(&f, "NEW.TXT", rb, sizeof rb), 5000);
    CHECK(!memcmp(rb, buf, 5000));
    CHECK_EQ(fat_read(&f, "HELLO.TXT", rb, sizeof rb), 1500);
    CHECK(!memcmp(rb, buf + 100, 1500));
    CHECK_EQ(fat_read(&f, "BIG.BIN", rb, sizeof rb), 5);
    names[0] = 0;
    fat_list(&f, list_cb, names);
    CHECK_STR(names, "BIG.BIN:5 HELLO.TXT:1500 NEW.TXT:5000 EMPTY:0 ");
    /* a fresh mount sees the same */
    CHECK_EQ(fat_mount(&f, (struct blkdev){img_read, img_write, &m}), FAT_OK);
    CHECK_EQ(fat_read(&f, "NEW.TXT", rb, sizeof rb), 5000);
    CHECK(!memcmp(rb, buf, 5000));
    snprintf(path, sizeof path, "%s/out%d.img", dir, bits);
    FILE *fp = fopen(path, "wb");
    fwrite(m.d, 1, m.n, fp);
    fclose(fp);
    free(m.d);
}

static void test_fat16(void) { run(16); }
static void test_fat32(void) { run(32); }

static void test_not_fat(void)
{
    static uint8_t blank[64 * 512];
    struct img m = {blank, sizeof blank, 0, 0};
    struct fat f;
    CHECK_EQ(fat_mount(&f, (struct blkdev){img_read, img_write, &m}), FAT_ENOFS);
}

int main(int argc, char **argv)
{
    dir = argc > 1 ? argv[1] : ".";
    char path[512];
    snprintf(path, sizeof path, "%s/big.bin", dir);
    uint8_t *b = load(path, &big_n);
    if (!b || big_n > sizeof big) {
        printf("no test data in %s\n", dir);
        return 1;
    }
    memcpy(big, b, big_n);
    free(b);
    RUN(test_not_fat);
    RUN(test_fat16);
    RUN(test_fat32);
    return TEST_RESULT();
}
