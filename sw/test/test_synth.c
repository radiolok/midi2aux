/* synth.c against a fake register file. */
#include <stdlib.h>

#include "unity_lite.h"

#include "../fw/params.c"
#include "../fw/patch.c"
#include "../fw/synth.c"
#include "../fw/voice_alloc.c"
#include "../lib/xprintf.c"

/* fake register space: 0x2000_0000 voices, 0x2001_0000 globals, 0x2002_0000 modulation */
static uint32_t regs[3 * 16384];
static uint32_t idx(uint32_t a) { return ((a >> 16) & 3) * 16384 + ((a & 0xFFFF) >> 2); }
void uart_putc(char c) { (void)c; }
void hw_write(uint32_t a, uint32_t v) { regs[idx(a)] = v; }
uint32_t hw_read(uint32_t a) { return regs[idx(a)]; }

static struct synth s;
static const struct fs_info FS = {99000000u, 16u};

static void init(int n)
{
    memset(regs, 0, sizeof regs);
    synth_init(&s, n, FS);
}

static void set_status(int v, int st, uint32_t level) { regs[idx(VOICE_REG(v, V_STATUS))] = (uint32_t)st << 20 | level; }

static void test_patch_registers(void)
{
    init(4);
    CHECK_EQ(hw_read(SYNTH_REG(S_WAVES)), 0);
    CHECK_EQ(hw_read(SYNTH_REG(S_CUTOFF)), hz_pitch(&FS, 4000));
    CHECK_EQ(hw_read(SYNTH_REG(S_RES_Q)), 65536);
    CHECK_EQ(hw_read(SYNTH_REG(S_A1)), env_coef(&FS, 5000, 1));
    CHECK_EQ(hw_read(SYNTH_REG(S_S2)), 19661);
    CHECK_EQ(hw_read(SYNTH_REG(S_MASTER)), 16384);
    synth_set_param(&s, P_CUTOFF, 100000); /* clamped to 16 kHz */
    CHECK_EQ(s.p.v[P_CUTOFF], 16000);
    CHECK_EQ(hw_read(SYNTH_REG(S_CUTOFF)), hz_pitch(&FS, 16000));
    synth_set_param(&s, P_WAVE1, 3);
    CHECK_EQ(hw_read(SYNTH_REG(S_WAVES)), 3);
}

static void test_param_table(void)
{
    char buf[32];
    CHECK_EQ(param_find("cutoff"), P_CUTOFF);
    CHECK_EQ(param_find("nope"), -1);
    for (int i = 0; i < P_COUNT; i++) {
        const struct param_desc *d = &param_table[i];
        CHECK(d->name && d->label && d->min <= d->def && d->def <= d->max);
        param_format(i, d->def, buf, sizeof buf);
        CHECK(buf[0] != 0);
    }
    param_format(P_LFO1_RATE, 550, buf, sizeof buf);
    CHECK_STR(buf, "5.50 Hz");
    param_format(P_FMODE, 2, buf, sizeof buf);
    CHECK_STR(buf, "hp");
}

static void test_note_on_off(void)
{
    init(4);
    int v = synth_midi(&s, 0x93, 69, 127);
    CHECK_EQ(v, 0);
    CHECK_EQ(hw_read(VOICE_REG(0, V_PITCH1)), hz_pitch(&FS, 440));
    CHECK_EQ(hw_read(VOICE_REG(0, V_PITCH2)) - hw_read(VOICE_REG(0, V_PITCH1)), cents_pitch(7));
    CHECK_EQ(hw_read(VOICE_REG(0, V_GATE)), 1);
    CHECK_EQ(hw_read(VOICE_REG(0, V_VEL_AMP)), 65536);
    CHECK_EQ(hw_read(VOICE_REG(0, V_CUT_OFS)), cents_pitch(1200));
    set_status(0, 1, 30000);
    CHECK_EQ(synth_midi(&s, 0x83, 69, 64), 0);
    CHECK_EQ(hw_read(VOICE_REG(0, V_GATE)), 0);
}

static void test_retrigger_toggles(void)
{
    init(4);
    synth_midi(&s, 0x90, 60, 100);
    set_status(0, 2, 40000);
    synth_midi(&s, 0x90, 60, 90); /* same note while held */
    CHECK_EQ(hw_read(VOICE_REG(0, V_GATE)), 3);
    synth_midi(&s, 0x90, 60, 90);
    CHECK_EQ(hw_read(VOICE_REG(0, V_GATE)), 1);
}

static void test_chord_uses_free_voices_and_steals(void)
{
    init(3);
    for (int i = 0; i < 3; i++) {
        int v = synth_midi(&s, 0x90, (uint8_t)(60 + 4 * i), 100);
        CHECK_EQ(v, i);
        set_status(v, 2, 50000);
    }
    CHECK_EQ(synth_midi(&s, 0x90, 80, 100), 0); /* oldest */
    CHECK_EQ(hw_read(VOICE_REG(0, V_GATE)), 3);  /* stolen while gated: retrigger */
}

static void test_bend_and_all_off(void)
{
    init(4);
    synth_midi(&s, 0xE0, 0x7F, 0x7F);
    CHECK_EQ((int32_t)hw_read(SYNTH_REG(S_PM)), (8191 * 2 * 65536) / 98304);
    synth_midi(&s, 0xE0, 0x00, 0x00);
    CHECK_EQ((int32_t)hw_read(SYNTH_REG(S_PM)), -2 * 65536 / 12);
    synth_midi(&s, 0x90, 60, 100);
    synth_midi(&s, 0x90, 64, 100);
    synth_midi(&s, 0xFC, 0, 0);
    CHECK_EQ(hw_read(VOICE_REG(0, V_GATE)) & 1, 0);
    CHECK_EQ(hw_read(VOICE_REG(1, V_GATE)) & 1, 0);
}

static void test_sustain(void)
{
    init(4);
    synth_midi(&s, 0x90, 60, 100);
    synth_midi(&s, 0xB0, 64, 127);
    synth_midi(&s, 0x80, 60, 0);
    CHECK_EQ(hw_read(VOICE_REG(0, V_GATE)), 1);
    synth_midi(&s, 0xB0, 64, 0);
    CHECK_EQ(hw_read(VOICE_REG(0, V_GATE)), 0);
}

static void test_modulation(void)
{
    init(4);
    CHECK_EQ(hw_read(MOD_REG(M_ROUTE(0))), DST_PM << 8 | SRC_MODWHEEL << 4 | SRC_LFO1);
    CHECK_EQ(hw_read(MOD_REG(M_DEPTH(0))), cents_pitch(50));
    CHECK_EQ(hw_read(MOD_REG(M_LFO_INC(0))), lfo_inc(&FS, 550));
    CHECK(labs((long)lfo_inc(&FS, 550) - (long)(5.5 * 4294967296.0 / 48339.84375)) <= 1);
    synth_midi(&s, 0xB0, 1, 127);
    CHECK_EQ(hw_read(MOD_REG(M_MODWHEEL)), 65536);
    synth_midi(&s, 0xB0, 1, 64);
    CHECK_EQ(hw_read(MOD_REG(M_MODWHEEL)), (64u << 16) / 127u);
    CHECK_EQ(hw_read(MOD_REG(M_GATE)), 0);
    synth_midi(&s, 0x90, 60, 100);
    int v = synth_midi(&s, 0x90, 64, 100);
    CHECK_EQ(hw_read(SYNTH_REG(S_ENV_VOICE)), (uint32_t)v);
    CHECK_EQ(hw_read(MOD_REG(M_GATE)), 1);
    synth_midi(&s, 0x80, 60, 0);
    CHECK_EQ(hw_read(MOD_REG(M_GATE)), 1);
    synth_midi(&s, 0x80, 64, 0);
    CHECK_EQ(hw_read(MOD_REG(M_GATE)), 0);
}

int main(void)
{
    RUN(test_modulation);
    RUN(test_param_table);
    RUN(test_patch_registers);
    RUN(test_note_on_off);
    RUN(test_retrigger_toggles);
    RUN(test_chord_uses_free_voices_and_steals);
    RUN(test_bend_and_all_off);
    RUN(test_sustain);
    return TEST_RESULT();
}
