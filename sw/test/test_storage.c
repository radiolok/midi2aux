/* presets and firmware update on an SD card model holding a FAT16 image (tools/fatimg.py). */
#include <stdio.h>
#include <stdlib.h>

#include "unity_lite.h"

#include "../fw/avk.c"
#include "../fw/fat.c"
#include "../fw/params.c"
#include "../fw/patch.c"
#include "../fw/preset.c"
#include "../fw/sd.c"
#include "../fw/storage.c"
#include "../fw/synth.c"
#include "../fw/voice_alloc.c"
#include "../lib/crc32.c"
#include "../lib/xprintf.c"
#include "../../fpga/sim/models/sd_card_model.h"
#include "fake_regs.h"

void uart_putc(char c) { (void)c; }

/* SPI flash stub */
static uint8_t flash[1 << 20];
void flash_erase_4k(int spi, uint32_t addr)
{
    (void)spi;
    memset(flash + (addr & ~4095u), 0xFF, 4096);
}
void flash_program(int spi, uint32_t addr, const void *src, size_t len)
{
    (void)spi;
    const uint8_t *p = src;
    for (size_t i = 0; i < len; i++)
        flash[addr + i] &= p[i];
}
void flash_read(int spi, uint32_t addr, void *dst, size_t len)
{
    (void)spi;
    memcpy(dst, flash + addr, len);
}

static struct sd_card card;
static int cs;
static uint8_t bx(void *ctx, uint8_t b) { (void)ctx; return cs ? sd_card_xfer(&card, b) : 0xFF; }
static void bsel(void *ctx, int on)
{
    (void)ctx;
    if (!on)
        sd_card_deselect(&card);
    cs = on;
}
static void bspeed(void *ctx, int fast) { (void)ctx; (void)fast; }

static struct synth s;
static struct storage st;
static const struct fs_info FS = {99000000u, 16u};
static uint8_t *img;
static size_t img_n;

static void setup(void)
{
    memset(regs, 0, sizeof regs);
    synth_init(&s, 4, FS);
    CHECK_EQ(storage_mount(&st, (struct sd){bx, bsel, bspeed, 0, 0, 0}), 0);
}

static void test_presets(void)
{
    setup();
    synth_set_param(&s, P_CUTOFF, 1234);
    synth_set_param(&s, P_DETUNE, -42);
    synth_set_param(&s, P_DLY1_TIME, 20000);
    synth_set_route(&s, 3, (struct mod_route){SRC_IN1, SRC_MODWHEEL, DST_CM, -123456});
    CHECK_EQ(storage_save(&st, &s, 7), FAT_OK);
    synth_init(&s, 4, FS); /* defaults */
    CHECK_EQ(s.p.v[P_CUTOFF], 4000);
    CHECK_EQ(storage_load(&st, &s, 7), P_COUNT);
    CHECK_EQ(s.p.v[P_CUTOFF], 1234);
    CHECK_EQ(s.p.v[P_DETUNE], -42);
    CHECK_EQ(s.p.v[P_DLY1_TIME], 20000);
    CHECK_EQ(s.routes[3].src, SRC_IN1);
    CHECK_EQ(s.routes[3].depth, -123456);
    CHECK_EQ(hw_read(SYNTH_REG(S_CUTOFF)), hz_pitch(&FS, 1234)); /* applied to the engine */
    CHECK_EQ(storage_load(&st, &s, 8), FAT_ENOENT);
}

static void test_preset_format(void)
{
    uint8_t buf[PRESET_MAX_BYTES + 8];
    synth_init(&s, 4, FS);
    int n = preset_pack(&s, buf);
    CHECK_EQ(n, PRESET_MAX_BYTES);
    CHECK_EQ(preset_unpack(&s, buf, 7), -1);
    buf[0] = 'X';
    CHECK_EQ(preset_unpack(&s, buf, n), -1);
    buf[0] = 'A';
    /* an unknown parameter (from another firmware version) is skipped */
    buf[8] ^= 0x5A;
    CHECK_EQ(preset_unpack(&s, buf, n), P_COUNT - 1);
    /* hashes of all names differ */
    for (int i = 0; i < P_COUNT; i++)
        for (int j = i + 1; j < P_COUNT; j++)
            CHECK(preset_hash(param_table[i].name) != preset_hash(param_table[j].name));
    char name[13];
    preset_name(42, name);
    CHECK_STR(name, "PRESET42.BIN");
}

static void list_cb(void *ctx, const char *name, uint32_t size)
{
    (void)size;
    strcat(ctx, name);
    strcat(ctx, " ");
}

static void test_list_and_fw_update(void)
{
    setup();
    char names[128] = "";
    CHECK_EQ(storage_list(&st, list_cb, names), FAT_OK);
    CHECK_STR(names, "BIG.BIN HELLO.TXT PRESET07.BIN ");
    CHECK_EQ(storage_fw_update(&st, SPI_FLASH, 0x10000, 30000), FAT_ENOENT);
    static uint8_t fw[3000];
    for (int i = 0; i < 3000; i++)
        fw[i] = (uint8_t)(i * 31 + 5);
    CHECK_EQ(fat_write(&st.fat, "FIRMWARE.BIN", fw, sizeof fw), FAT_OK);
    CHECK_EQ(storage_fw_update(&st, SPI_FLASH, 0x10000, 1000), -10);
    memset(flash, 0xAB, sizeof flash);
    CHECK_EQ(storage_fw_update(&st, SPI_FLASH, 0x10000, 30000), 3000);
    struct fw_header h;
    memcpy(&h, flash + 0x10000, sizeof h);
    CHECK_EQ(h.magic, FW_MAGIC);
    CHECK_EQ(h.len, 3000);
    CHECK_EQ(h.crc, crc32(fw, sizeof fw));
    CHECK(!memcmp(flash + 0x10000 + FW_HDR_SIZE, fw, sizeof fw));
}

static void test_no_card(void)
{
    struct storage none;
    memset(&none, 0, sizeof none);
    CHECK_EQ(storage_save(&none, &s, 1), SD_ENOCARD);
    CHECK_EQ(storage_load(&none, &s, 1), SD_ENOCARD);
}

int main(int argc, char **argv)
{
    char path[512];
    snprintf(path, sizeof path, "%s/fat16.img", argc > 1 ? argv[1] : ".");
    FILE *fp = fopen(path, "rb");
    if (!fp) {
        printf("no %s\n", path);
        return 1;
    }
    fseek(fp, 0, SEEK_END);
    img_n = (size_t)ftell(fp);
    fseek(fp, 0, SEEK_SET);
    img = malloc(img_n);
    if (fread(img, 1, img_n, fp) != img_n)
        return 1;
    fclose(fp);
    sd_card_init(&card, img, img_n, 1);
    RUN(test_presets);
    RUN(test_preset_format);
    RUN(test_list_and_fw_update);
    RUN(test_no_card);
    CHECK_EQ(card.errors, 0);
    free(img);
    return TEST_RESULT();
}
