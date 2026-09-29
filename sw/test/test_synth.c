/* synth.c against a fake register file. */
#include <stdlib.h>

#include "unity_lite.h"

#include "../fw/params.c"
#include "../fw/patch.c"
#include "../fw/synth.c"
#include "../fw/avk.c"
#include "../fw/voice_alloc.c"
#include "../lib/xprintf.c"


#include "fake_regs.h"
void uart_putc(char c) { (void)c; }

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
    CHECK_EQ(hw_read(SYNTH_REG(S_BLEP)), 0);
    synth_set_param(&s, P_BLEP, 1);
    CHECK_EQ(hw_read(SYNTH_REG(S_BLEP)), 1);
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

static void init_avk(void)
{
    memset(regs, 0, sizeof regs);
    static const uint8_t types[] = {SLOT_MATH, SLOT_MATH, SLOT_DELAY, SLOT_DELAY, SLOT_CHORUS, SLOT_REVERB};
    for (int k = 0; k < 6; k++)
        regs[idx(SLOT_REG(k, SL_TYPE))] = types[k];
    regs[idx(SYSINFO_NUM_SLOTS)] = 6;
    regs[idx(SYSINFO_MEM_WORDS)] = REVERB_WORDS + CHORUS_WORDS + 1000;
    synth_init(&s, 4, FS);
}

static void test_avk_defaults(void)
{
    init(4); /* no slots in the hardware: nothing enabled */
    CHECK_EQ(s.nslots, 0);
    init_avk();
    CHECK_EQ(s.nslots, 6);
    CHECK_EQ(s.cho_slot, 4);
    CHECK_EQ(s.rev_slot, 5);
    CHECK_EQ(hw_read(SLOT_REG(5, SL_MEM_BASE)), 0); /* reverb, chorus: fixed sizes first */
    CHECK_EQ(hw_read(SLOT_REG(5, SL_MEM_SIZE)), REVERB_WORDS);
    CHECK_EQ(hw_read(SLOT_REG(4, SL_MEM_BASE)), REVERB_WORDS);
    CHECK_EQ(hw_read(SLOT_REG(4, SL_MEM_SIZE)), CHORUS_WORDS);
    CHECK_EQ(s.math_slot[0], 0);
    CHECK_EQ(s.math_slot[1], 1);
    CHECK_EQ(s.dly_slot[0], 2);
    CHECK_EQ(s.dly_slot[1], 3);
    CHECK_EQ(hw_read(SLOT_REG(2, SL_MEM_BASE)), REVERB_WORDS + CHORUS_WORDS); /* the delays split the rest */
    CHECK_EQ(hw_read(SLOT_REG(2, SL_MEM_SIZE)), 500);
    CHECK_EQ(hw_read(SLOT_REG(3, SL_MEM_BASE)), REVERB_WORDS + CHORUS_WORDS + 500);
    CHECK_EQ(hw_read(SLOT_REG(3, SL_MEM_SIZE)), 500);
    CHECK_EQ(hw_read(BUS_OUT2_SEL), BUS_LFO1);
    CHECK_EQ(hw_read(BUS_OUT2_GAIN), 65536);
    CHECK_EQ(hw_read(BUS_GAIN(BUS_IN1)), 0);
    for (int k = 0; k < 6; k++) /* MATH off, effects at level 0 */
        CHECK_EQ(hw_read(BUS_GAIN(BUS_SLOT0 + k)), 0);
    CHECK_EQ(hw_read(SLOT_REG(0, SL_BYPASS)), 1);
    CHECK_EQ(hw_read(SLOT_REG(2, SL_BYPASS)), 0); /* delays keep running */
}

static void test_avk_delay(void)
{
    init_avk();
    /* 250 ms at fs = 99e6 / 2048 */
    CHECK_EQ(hw_read(SLOT_REG(2, SL_PARAM(0))), 12085);
    CHECK_EQ(hw_read(SLOT_REG(2, SL_SEL_A)), BUS_IN1);
    CHECK_EQ(hw_read(SLOT_REG(3, SL_SEL_A)), BUS_IN2);
    CHECK_EQ(hw_read(SLOT_REG(2, SL_PARAM(1))), 26214); /* feedback 40 % */
    CHECK_EQ(hw_read(SLOT_REG(2, SL_PARAM(2))), 65536); /* wet only */
    CHECK_EQ(hw_read(SLOT_REG(2, SL_PARAM(3))), 0);
    synth_set_param(&s, P_DLY2_TIME, 1000);
    CHECK_EQ(hw_read(SLOT_REG(3, SL_PARAM(0))), 48340);
    synth_set_param(&s, P_DLY2_LVL, 100);
    synth_set_param(&s, P_FX_MIX, 50);
    CHECK_EQ(hw_read(BUS_GAIN(BUS_SLOT0 + 3)), 32768);
    synth_set_param(&s, P_DLY1_SRC, BUS_SYNTH);
    CHECK_EQ(hw_read(SLOT_REG(2, SL_SEL_A)), BUS_SYNTH);
    /* delay time from the SYNC period: 2 Hz = 24170 samples */
    synth_set_param(&s, P_DLY_SYNC, 1);
    regs[idx(PERIPH_ADDR(9, 0x04))] = 49500000;
    regs[idx(PERIPH_ADDR(9, 0x08))] += 1;
    avk_poll(&s);
    CHECK_EQ(hw_read(SLOT_REG(2, SL_PARAM(0))), 24170);
    CHECK_EQ(hw_read(SLOT_REG(3, SL_PARAM(0))), 24170);
    synth_set_param(&s, P_DLY_SYNC, 0);
    CHECK_EQ(hw_read(SLOT_REG(3, SL_PARAM(0))), 48340);
}

static void test_avk_slots_and_out2(void)
{
    init_avk();
    synth_set_param(&s, P_SLOT2_OP, 1 + MATH_MUL);
    synth_set_param(&s, P_SLOT2_A, BUS_IN1);
    synth_set_param(&s, P_SLOT2_B, BUS_IN2);
    synth_set_param(&s, P_SLOT2_K, -50);
    synth_set_param(&s, P_FX_MIX, 100);
    CHECK_EQ(hw_read(SLOT_REG(1, SL_BYPASS)), 0);
    CHECK_EQ(hw_read(SLOT_REG(0, SL_BYPASS)), 1);
    CHECK_EQ(hw_read(SLOT_REG(1, SL_PARAM(0))), MATH_MUL);
    CHECK_EQ((int32_t)hw_read(SLOT_REG(1, SL_PARAM(1))), -32768);
    CHECK_EQ(hw_read(SLOT_REG(1, SL_SEL_A)), BUS_IN1);
    CHECK_EQ(hw_read(BUS_GAIN(BUS_SLOT0 + 1)), 65536);
    CHECK_EQ(hw_read(BUS_GAIN(BUS_SLOT0)), 0);
    synth_set_param(&s, P_FX_MIX, 25);
    CHECK_EQ(hw_read(BUS_GAIN(BUS_SLOT0 + 1)), 16384);
    synth_set_param(&s, P_IN1_MIX, -100);
    CHECK_EQ((int32_t)hw_read(BUS_GAIN(BUS_IN1)), -65536);
    synth_set_param(&s, P_OUT2_SRC, BUS_GATE);
    synth_set_param(&s, P_OUT2_GAIN, 200);
    CHECK_EQ(hw_read(BUS_OUT2_SEL), BUS_GATE);
    CHECK_EQ(hw_read(BUS_OUT2_GAIN), 131072);
}

static int voice_of(uint8_t note)
{
    for (int v = 0; v < s.va.n; v++)
        if (s.va.v[v].note == note && s.va.v[v].held)
            return v;
    return -1;
}

static void test_avk_sync(void)
{
    init_avk();
    uint32_t *edges = &regs[idx(PERIPH_ADDR(9, 0x08))];
    CHECK_EQ(avk_poll(&s), 0);
    *edges += 1; /* SYNC_OFF: edges are only counted */
    CHECK_EQ(avk_poll(&s), 1);
    CHECK_EQ(s.sync_note, -1);
    synth_set_param(&s, P_SYNC_MODE, SYNC_LFO);
    CHECK_EQ(hw_read(MOD_REG(M_LFO_CFG(0))) >> 4 & 1, 1);
    CHECK_EQ(hw_read(MOD_REG(M_LFO_CFG(1))) >> 4 & 1, 1);
    synth_set_param(&s, P_SYNC_MODE, SYNC_NOTE);
    CHECK_EQ(hw_read(MOD_REG(M_LFO_CFG(0))) >> 4 & 1, 0);
    *edges += 1;
    avk_poll(&s);
    CHECK_EQ(s.sync_note, 60);
    int v = voice_of(60);
    CHECK(v >= 0);
    CHECK_EQ(hw_read(VOICE_REG(v, V_GATE)) & 1, 1);
    uint32_t rt = hw_read(VOICE_REG(v, V_GATE)) >> 1 & 1;
    *edges += 3; /* the next edge retriggers the same note */
    avk_poll(&s);
    CHECK_EQ(voice_of(60), v);
    CHECK_EQ(hw_read(VOICE_REG(v, V_GATE)) >> 1 & 1, rt ^ 1);
    CHECK_EQ(hw_read(MOD_REG(M_GATE)), 1);
    synth_set_param(&s, P_SYNC_MODE, SYNC_OFF); /* releases the note */
    CHECK_EQ(s.sync_note, -1);
    CHECK_EQ(hw_read(VOICE_REG(v, V_GATE)) & 1, 0);
    regs[idx(PERIPH_ADDR(9, 0x04))] = 99000; /* 1 kHz */
    CHECK_EQ(avk_sync_hz100(&s), 100000);
}

static void test_avk_calibration(void)
{
    init_avk();
    regs[idx(ADC_RAW(1))] = 2051;
    avk_cal_zero(1);
    CHECK_EQ(hw_read(ADC_OFFSET(1)), 2051);
    regs[idx(ADC_RAW(1))] = 2051 + 1638; /* +10 V ideally: 1638.4 codes */
    CHECK_EQ(avk_cal_ref(1, 10000), 1);
    uint32_t g = hw_read(ADC_GAIN(1));
    CHECK(llabs((((int64_t)1638 * g) >> 16) - 65536) <= 1);
    regs[idx(ADC_RAW(1))] = 2051;
    CHECK_EQ(avk_cal_ref(1, 10000), 0);
}

static void test_avk_chorus_reverb(void)
{
    init_avk();
    CHECK_EQ(hw_read(SLOT_REG(4, SL_PARAM(0))), 338); /* 7 ms */
    CHECK_EQ(hw_read(SLOT_REG(4, SL_PARAM(1))), 145); /* 3 ms */
    CHECK_EQ(hw_read(SLOT_REG(4, SL_PARAM(2))), lfo_inc(&FS, 50));
    synth_set_param(&s, P_CHO_LVL, 100);
    synth_set_param(&s, P_FX_MIX, 100);
    CHECK_EQ(hw_read(BUS_GAIN(BUS_SLOT0 + 4)), 65536);
    synth_set_param(&s, P_REV_ROOM, 100);
    synth_set_param(&s, P_REV_DAMP, 100);
    CHECK_EQ(hw_read(SLOT_REG(5, SL_PARAM(0))), 64225);
    CHECK_EQ(hw_read(SLOT_REG(5, SL_PARAM(1))), 26214);
    synth_set_param(&s, P_REV_SRC, BUS_IN2);
    CHECK_EQ(hw_read(SLOT_REG(5, SL_SEL_A)), BUS_IN2);
    /* too little memory for the reverb: it gets none */
    memset(regs, 0, sizeof regs);
    regs[idx(SLOT_REG(0, SL_TYPE))] = SLOT_REVERB;
    regs[idx(SYSINFO_NUM_SLOTS)] = 1;
    regs[idx(SYSINFO_MEM_WORDS)] = 4096;
    synth_init(&s, 4, FS);
    CHECK_EQ(hw_read(SLOT_REG(0, SL_MEM_SIZE)), 0);
}

static void test_hsync_follower_pitch_cv(void)
{
    init_avk();
    synth_set_param(&s, P_HSYNC, 2);
    CHECK_EQ(hw_read(SYNTH_REG(S_HSYNC)), 2);
    synth_set_param(&s, P_FOLLOW_SRC, 1);
    CHECK_EQ(hw_read(MOD_REG(M_FOLLOW_SRC)), 1);
    /* 1 - e^(-1 / (5 ms * fs)) = 0.004128 */
    CHECK(llabs((long long)hw_read(MOD_REG(M_FOLLOW_ATK)) - 271) <= 1);
    CHECK(llabs((long long)hw_read(MOD_REG(M_FOLLOW_REL)) - 14) <= 1);
    CHECK_EQ(avk_pitch_cv(60), 0);
    CHECK_EQ(avk_pitch_cv(72), 6554); /* +1 V */
    CHECK_EQ(avk_pitch_cv(48), -6554);
    synth_set_param(&s, P_OUT2_SRC, OUT2_PITCH);
    CHECK_EQ(hw_read(BUS_OUT2_GAIN), 0);
    synth_midi(&s, 0x90, 67, 100);
    CHECK_EQ((int32_t)hw_read(BUS_OUT2_DC), avk_pitch_cv(67));
    synth_set_param(&s, P_OUT2_SRC, BUS_LFO1);
    CHECK_EQ(hw_read(BUS_OUT2_DC), 0);
}

int main(void)
{
    RUN(test_avk_chorus_reverb);
    RUN(test_hsync_follower_pitch_cv);
    RUN(test_avk_defaults);
    RUN(test_avk_slots_and_out2);
    RUN(test_avk_delay);
    RUN(test_avk_sync);
    RUN(test_avk_calibration);
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
