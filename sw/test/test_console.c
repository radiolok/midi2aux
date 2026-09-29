#include <stdio.h>
#include <stdlib.h>

#include "unity_lite.h"

#include "../fw/console.c"
#include "../fw/params.c"
#include "../fw/patch.c"
#include "../fw/synth.c"
#include "../fw/avk.c"
#include "../fw/voice_alloc.c"
#include "../lib/xprintf.c"
#include "../fw/fat.c"
#include "../fw/preset.c"
#include "../fw/sd.c"
#include "../fw/storage.c"
#include "../lib/crc32.c"
#include "../../fpga/sim/models/sd_card_model.h"

#include "fake_regs.h"
void uart_putc(char c) { (void)c; }
void ui_row_text(const struct ui *u, int r, char *b, int n) /* no UI in this test */
{
    (void)u, (void)r;
    if (n)
        b[0] = 0;
}

static char out[4096];
void log_printf(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    size_t n = strlen(out);
    xvsnprintf(out + n, sizeof out - n, fmt, ap);
    va_end(ap);
}

static struct synth s;
static const struct fs_info FS = {99000000u, 16u};

static void feed(const char *t)
{
    out[0] = 0;
    while (*t)
        console_feed(*t++);
}

static void test_set_get(void)
{
    synth_init(&s, 4, FS);
    console_init(&s, 0);
    feed("set cutoff 1000\r\n");
    CHECK_STR(out, "ok cutoff = 1000 (1000 Hz)\n");
    CHECK_EQ(hw_read(SYNTH_REG(S_CUTOFF)), hz_pitch(&FS, 1000));
    feed("set  mix2   -5\n");
    CHECK_STR(out, "ok mix2 = 0 (0 %)\n");
    feed("get lfo1wave\n");
    CHECK_STR(out, "lfo1wave = 0 (sine)\n");
    feed("set bogus 1\n");
    CHECK(strstr(out, "error") != 0);
    feed("set cutoff 12x\n");
    CHECK(strstr(out, "error") != 0);
}

static void test_route_and_notes(void)
{
    synth_init(&s, 4, FS);
    console_init(&s, 0);
    feed("route 2 2 0 2 -65536\n");
    CHECK_STR(out, "ok route 2\n");
    CHECK_EQ(hw_read(MOD_REG(M_ROUTE(2))), DST_CM << 8 | SRC_LFO2);
    CHECK_EQ(hw_read(MOD_REG(M_DEPTH(2))), 0xFF0000u);
    feed("route 0 1 0 1 5\n");
    CHECK(strstr(out, "error") != 0);
    feed("note 69 127\n");
    CHECK_STR(out, "ok note 69 v=0\n");
    CHECK_EQ(hw_read(VOICE_REG(0, V_GATE)), 1);
    feed("off 69\n");
    CHECK_EQ(hw_read(VOICE_REG(0, V_GATE)), 0);
    regs[idx(PERIPH_ADDR(7, 4))] = (uint32_t)-2;
    regs[idx(PERIPH_ADDR(6, 0))] = 4095u << 4;
    feed("panel\n");
    CHECK_STR(out, "enc 0 -2 0 0 buttons 0 pots 4095 0 0 0 0 0 0 0\n");
    feed("list\n");
    CHECK(strstr(out, "master = 25 (25 %)") != 0);
}

static void test_avk(void)
{
    synth_init(&s, 4, FS);
    console_init(&s, 0);
    regs[idx(ADC_RAW(0))] = 2100;
    regs[idx(ADC_IN(0))] = 2080;
    regs[idx(PERIPH_ADDR(9, 0x04))] = 198000; /* 500 Hz */
    regs[idx(PERIPH_ADDR(9, 0x08))] = 7;
    feed("avk\n");
    CHECK_STR(out, "in1 raw 2100 val 2080 in2 raw 0 val 0 sync 500.00 Hz edges 7\nbus 0 0 0 0 0 0 0 0\n");
    feed("cal 1 zero\n");
    CHECK_STR(out, "ok cal in1 offset 2100 gain 0\n");
    regs[idx(ADC_RAW(0))] = 2100 + 1000;
    feed("cal 1 5000\n");
    CHECK(!strncmp(out, "ok cal in1 offset 2100 gain ", 28));
    CHECK_EQ(hw_read(ADC_GAIN(0)), (uint32_t)((5000ll << 32) / 10000000));
    regs[idx(ADC_RAW(0))] = 2100;
    feed("cal 1 5000\n");
    CHECK(strstr(out, "error") != 0);
    feed("cal 3 zero\n");
    CHECK(strstr(out, "error") != 0);
}

static void test_mem(void)
{
    synth_init(&s, 4, FS);
    console_init(&s, 0);
    feed("mem 5 -1234\n");
    CHECK_STR(out, "ok mem 5 = -1234\n");
    CHECK_EQ(hw_read(XRAM_BASE + 20), (uint32_t)-1234);
    feed("mem 5\n");
    CHECK_STR(out, "ok mem 5 = -1234\n");
    feed("mem 5 x\n");
    CHECK(strstr(out, "error") != 0);
}

/* SD card: the model with a FAT16 image; flash: an array */
static uint8_t flash[1 << 20];
void flash_erase_4k(int spi, uint32_t addr) { (void)spi; memset(flash + (addr & ~4095u), 0xFF, 4096); }
void flash_program(int spi, uint32_t addr, const void *src, size_t len) { (void)spi; memcpy(flash + addr, src, len); }
void flash_read(int spi, uint32_t addr, void *dst, size_t len) { (void)spi; memcpy(dst, flash + addr, len); }
static struct sd_card card;
static int cs;
static uint8_t bx(void *ctx, uint8_t b) { (void)ctx; return cs ? sd_card_xfer(&card, b) : 0xFF; }
static void bsel(void *ctx, int on) { (void)ctx; if (!on) sd_card_deselect(&card); cs = on; }
static void bspeed(void *ctx, int fast) { (void)ctx; (void)fast; }
static const char *img_dir = ".";

static void test_storage_commands(void)
{
    static struct storage st;
    char path[512];
    size_t n = 0;
    snprintf(path, sizeof path, "%s/fat16.img", img_dir);
    FILE *fp = fopen(path, "rb");
    CHECK(fp != 0);
    if (!fp)
        return;
    uint8_t *img = malloc(40u << 20);
    n = fread(img, 1, 40u << 20, fp);
    fclose(fp);
    sd_card_init(&card, img, n, 1);
    synth_init(&s, 4, FS);
    console_init(&s, 0);
    feed("ls\n");
    CHECK(strstr(out, "error") != 0); /* no storage yet */
    console_set_storage(&st, (struct sd){bx, bsel, bspeed, 0, 0, 0});
    feed("ls\n");
    CHECK(strstr(out, "error: ls") != 0); /* not mounted */
    feed("sd\n");
    CHECK_STR(out, "ok sd fat16\n");
    feed("set cutoff 777\n");
    feed("save 3\n");
    CHECK_STR(out, "ok save 3\n");
    feed("save 100\n");
    CHECK(strstr(out, "error") != 0);
    feed("ls\n");
    char want[128];
    snprintf(want, sizeof want, "file BIG.BIN 3000\nfile HELLO.TXT 6\nfile PRESET03.BIN %d\nok ls\n", PRESET_MAX_BYTES);
    CHECK_STR(out, want);
    feed("set cutoff 5000\n");
    feed("load 3\n");
    CHECK_STR(out, "ok load 3\n");
    CHECK_EQ(s.p.v[P_CUTOFF], 777);
    feed("load 4\n");
    CHECK_STR(out, "error: load -3\n");
    feed("fwupdate\n");
    CHECK_STR(out, "error: fwupdate -3\n");
    CHECK_EQ(card.errors, 0);
    free(img);
}

static void test_long_line_truncated(void)
{
    console_init(&s, 0);
    feed("set cutoff 1000 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n");
    CHECK(strstr(out, "error") != 0);
    feed("help\n");
    CHECK(strstr(out, "route") != 0);
}

int main(int argc, char **argv)
{
    if (argc > 1)
        img_dir = argv[1];
    RUN(test_storage_commands);
    RUN(test_avk);
    RUN(test_mem);
    RUN(test_set_get);
    RUN(test_route_and_notes);
    RUN(test_long_line_truncated);
    return TEST_RESULT();
}
