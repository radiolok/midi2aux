#include <stdlib.h>

#include "unity_lite.h"

#include "../fw/console.c"
#include "../fw/params.c"
#include "../fw/patch.c"
#include "../fw/synth.c"
#include "../fw/voice_alloc.c"
#include "../lib/xprintf.c"

static uint32_t regs[3 * 16384];
static uint32_t idx(uint32_t a) { return ((a >> 16) & 3) * 16384 + ((a & 0xFFFF) >> 2); }
void hw_write(uint32_t a, uint32_t v) { regs[idx(a)] = v; }
uint32_t hw_read(uint32_t a) { return regs[idx(a)]; }
void uart_putc(char c) { (void)c; }

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
    console_init(&s);
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
    console_init(&s);
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
    feed("list\n");
    CHECK(strstr(out, "master = 25 (25 %)") != 0);
}

static void test_long_line_truncated(void)
{
    console_init(&s);
    feed("set cutoff 1000 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n");
    CHECK(strstr(out, "error") != 0);
    feed("help\n");
    CHECK(strstr(out, "route") != 0);
}

int main(void)
{
    RUN(test_set_get);
    RUN(test_route_and_notes);
    RUN(test_long_line_truncated);
    return TEST_RESULT();
}
