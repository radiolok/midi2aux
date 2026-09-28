#include <stdlib.h>

#include "unity_lite.h"

#include "../fw/console.c"
#include "../fw/params.c"
#include "../fw/patch.c"
#include "../fw/synth.c"
#include "../fw/avk.c"
#include "../fw/voice_alloc.c"
#include "../lib/xprintf.c"

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

static void test_long_line_truncated(void)
{
    console_init(&s, 0);
    feed("set cutoff 1000 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n");
    CHECK(strstr(out, "error") != 0);
    feed("help\n");
    CHECK(strstr(out, "route") != 0);
}

int main(void)
{
    RUN(test_avk);
    RUN(test_set_get);
    RUN(test_route_and_notes);
    RUN(test_long_line_truncated);
    return TEST_RESULT();
}
