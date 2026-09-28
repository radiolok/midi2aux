/* synth.c against a fake register file. */
#include "unity_lite.h"

#include "../fw/params.c"
#include "../fw/synth.c"
#include "../fw/voice_alloc.c"

#define NREG 0x20000
static uint32_t regs[NREG / 4 * 2];
static uint32_t idx(uint32_t a) { return ((a >> 16) & 1) * (NREG / 4) + ((a & 0xFFFF) >> 2); }
void hw_write(uint32_t a, uint32_t v) { regs[idx(a)] = v; }
uint32_t hw_read(uint32_t a) { return regs[idx(a)]; }

static struct synth s;
static const struct fs_info FS = {99000000u, 16u};

static void init(int n)
{
    memset(regs, 0, sizeof regs);
    synth_init(&s, n, FS, &default_patch);
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

int main(void)
{
    RUN(test_patch_registers);
    RUN(test_note_on_off);
    RUN(test_retrigger_toggles);
    RUN(test_chord_uses_free_voices_and_steals);
    RUN(test_bend_and_all_off);
    RUN(test_sustain);
    return TEST_RESULT();
}
