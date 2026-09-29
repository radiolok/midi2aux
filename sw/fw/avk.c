/* AVK link: signal bus gains, effect slots, OUT2, SYNC modes, input calibration.
 * Register access goes through hw_write / hw_read (host-testable). */
#include "hw.h"
#include "synth.h"

static int32_t pct_q16s(int32_t pct) { return pct * 65536 / 100; }

void avk_init(struct synth *s)
{
    uint32_t n = hw_read(SYSINFO_NUM_SLOTS), words = hw_read(SYSINFO_MEM_WORDS), used = 0;
    int nm = 0, nd = 0, ndly = 0;
    s->nslots = (int)(n > AVK_MAX_SLOTS ? AVK_MAX_SLOTS : n);
    for (int k = 0; k < AVK_PATCH_SLOTS; k++)
        s->math_slot[k] = s->dly_slot[k] = -1;
    s->cho_slot = s->rev_slot = -1;
    for (int k = 0; k < s->nslots; k++) {
        uint8_t t = (uint8_t)hw_read(SLOT_REG(k, SL_TYPE));
        s->slot_type[k] = t;
        ndly += t == SLOT_DELAY;
        if (t == SLOT_MATH && nm < AVK_PATCH_SLOTS)
            s->math_slot[nm++] = (int8_t)k;
        if (t == SLOT_CHORUS && s->cho_slot < 0)
            s->cho_slot = (int8_t)k;
        if (t == SLOT_REVERB && s->rev_slot < 0)
            s->rev_slot = (int8_t)k;
    }
    /* external memory: the reverb and the chorus take fixed sizes, the delays share the rest */
    if (s->rev_slot >= 0 && words - used >= REVERB_WORDS) {
        hw_write(SLOT_REG(s->rev_slot, SL_MEM_BASE), used);
        hw_write(SLOT_REG(s->rev_slot, SL_MEM_SIZE), REVERB_WORDS);
        used += REVERB_WORDS;
    }
    if (s->cho_slot >= 0 && words - used >= CHORUS_WORDS) {
        hw_write(SLOT_REG(s->cho_slot, SL_MEM_BASE), used);
        hw_write(SLOT_REG(s->cho_slot, SL_MEM_SIZE), CHORUS_WORDS);
        used += CHORUS_WORDS;
    }
    for (int k = 0; k < s->nslots; k++)
        if (s->slot_type[k] == SLOT_DELAY) {
            uint32_t size = (words - used) / (uint32_t)ndly;
            hw_write(SLOT_REG(k, SL_MEM_BASE), used + (uint32_t)nd * size);
            hw_write(SLOT_REG(k, SL_MEM_SIZE), size);
            if (nd < AVK_PATCH_SLOTS)
                s->dly_slot[nd] = (int8_t)k;
            nd++;
        }
    s->sync_edges = hw_read(PERIPH_ADDR(9, 0x08));
    s->sync_note = -1;
    s->sync_samples = 0;
}

static uint32_t ms_samples(const struct synth *s, int32_t ms)
{
    return (uint32_t)(((uint64_t)(uint32_t)ms * s->fs.sys_clk + 64000u * s->fs.bck_half) /
                      (128000u * s->fs.bck_half));
}

static uint64_t us_per_sample_q24(const struct synth *s)
{
    return (((uint64_t)128000000u * s->fs.bck_half << 24) + s->fs.sys_clk / 2) / s->fs.sys_clk;
}

/* one-pole coefficient 1 - e^(-1 / (time * fs)), Q0.16 (series to x^2: x <= 0.02) */
static uint32_t follow_coef(const struct synth *s, int32_t ms)
{
    uint64_t x = (us_per_sample_q24(s) << 8) / (uint64_t)(1000 * ms); /* Q32 */
    return (uint32_t)((x - ((x * x) >> 33) + (1u << 15)) >> 16);
}

int32_t avk_pitch_cv(int note)
{
    /* 1 V/octave = 0.1 machine unit per 12 semitones */
    int32_t d = (note - 60) * 65536;
    return d >= 0 ? (d + 60) / 120 : (d - 60) / 120;
}

static uint32_t dly_time(const struct synth *s, int n)
{
    if (s->p.v[P_DLY_SYNC] && s->sync_samples)
        return s->sync_samples;
    return ms_samples(s, s->p.v[P_DLY1_TIME + n * DLY_PARAMS]);
}

void avk_apply(struct synth *s)
{
    const int32_t *v = s->p.v;
    hw_write(BUS_GAIN(BUS_IN1), (uint32_t)pct_q16s(v[P_IN1_MIX]));
    hw_write(BUS_GAIN(BUS_IN2), (uint32_t)pct_q16s(v[P_IN2_MIX]));
    for (int k = 0; k < s->nslots; k++) { /* slots the patch does not use: off */
        hw_write(SLOT_REG(k, SL_BYPASS), 1);
        hw_write(BUS_GAIN(BUS_SLOT0 + k), 0);
    }
    for (int n = 0; n < AVK_PATCH_SLOTS; n++) {
        int k = s->math_slot[n];
        if (k >= 0) {
            const int32_t *sp = &v[P_SLOT1_OP + n * SLOT_PARAMS]; /* OP, A, B, K */
            hw_write(SLOT_REG(k, SL_SEL_A), (uint32_t)sp[1]);
            hw_write(SLOT_REG(k, SL_SEL_B), (uint32_t)sp[2]);
            if (sp[0]) {
                hw_write(SLOT_REG(k, SL_PARAM(0)), (uint32_t)(sp[0] - 1));
                hw_write(SLOT_REG(k, SL_PARAM(1)), (uint32_t)pct_q16s(sp[3]));
                hw_write(SLOT_REG(k, SL_BYPASS), 0);
                hw_write(BUS_GAIN(BUS_SLOT0 + k), (uint32_t)pct_q16s(v[P_FX_MIX]));
            }
        }
        k = s->dly_slot[n];
        if (k >= 0) {
            const int32_t *dp = &v[P_DLY1_SRC + n * DLY_PARAMS]; /* SRC, TIME, FB, LVL */
            hw_write(SLOT_REG(k, SL_SEL_A), (uint32_t)dp[0]);
            hw_write(SLOT_REG(k, SL_PARAM(0)), dly_time(s, n));
            hw_write(SLOT_REG(k, SL_PARAM(1)), (uint32_t)pct_q16s(dp[2]));
            hw_write(SLOT_REG(k, SL_PARAM(2)), Q16_ONE); /* wet only: the dry signal is mixed directly */
            hw_write(SLOT_REG(k, SL_PARAM(3)), 0);
            hw_write(SLOT_REG(k, SL_BYPASS), 0);
            hw_write(BUS_GAIN(BUS_SLOT0 + k), (uint32_t)(pct_q16s(dp[3]) * v[P_FX_MIX] / 100));
        }
    }
    if (s->cho_slot >= 0) {
        int k = s->cho_slot;
        hw_write(SLOT_REG(k, SL_SEL_A), (uint32_t)v[P_CHO_SRC]);
        hw_write(SLOT_REG(k, SL_PARAM(0)), ms_samples(s, v[P_CHO_BASE]) / 10u);
        hw_write(SLOT_REG(k, SL_PARAM(1)), ms_samples(s, v[P_CHO_DEPTH]) / 10u);
        hw_write(SLOT_REG(k, SL_PARAM(2)), lfo_inc(&s->fs, (uint32_t)v[P_CHO_RATE]));
        hw_write(SLOT_REG(k, SL_PARAM(3)), (uint32_t)pct_q16s(v[P_CHO_FB]));
        hw_write(SLOT_REG(k, SL_PARAM(4)), Q16_ONE);
        hw_write(SLOT_REG(k, SL_PARAM(5)), 0);
        hw_write(SLOT_REG(k, SL_BYPASS), 0);
        hw_write(BUS_GAIN(BUS_SLOT0 + k), (uint32_t)(pct_q16s(v[P_CHO_LVL]) * v[P_FX_MIX] / 100));
    }
    if (s->rev_slot >= 0) {
        int k = s->rev_slot;
        hw_write(SLOT_REG(k, SL_SEL_A), (uint32_t)v[P_REV_SRC]);
        hw_write(SLOT_REG(k, SL_PARAM(0)), (uint32_t)(45875 + 18350 * v[P_REV_ROOM] / 100)); /* 0.7..0.98 */
        hw_write(SLOT_REG(k, SL_PARAM(1)), (uint32_t)(26214 * v[P_REV_DAMP] / 100));        /* 0..0.4 */
        hw_write(SLOT_REG(k, SL_PARAM(2)), Q16_ONE);
        hw_write(SLOT_REG(k, SL_PARAM(3)), 0);
        hw_write(SLOT_REG(k, SL_BYPASS), 0);
        hw_write(BUS_GAIN(BUS_SLOT0 + k), (uint32_t)(pct_q16s(v[P_REV_LVL]) * v[P_FX_MIX] / 100));
    }
    if (v[P_OUT2_SRC] == OUT2_PITCH) { /* the CV is written on note on (OUT2_DC) */
        hw_write(BUS_OUT2_GAIN, 0);
    } else {
        hw_write(BUS_OUT2_SEL, (uint32_t)v[P_OUT2_SRC]);
        hw_write(BUS_OUT2_GAIN, (uint32_t)pct_q16s(v[P_OUT2_GAIN]));
        hw_write(BUS_OUT2_DC, 0);
    }
    hw_write(SYNTH_REG(S_HSYNC), (uint32_t)v[P_HSYNC]);
    hw_write(MOD_REG(M_FOLLOW_SRC), (uint32_t)v[P_FOLLOW_SRC]);
    hw_write(MOD_REG(M_FOLLOW_ATK), follow_coef(s, v[P_FOLLOW_ATK]));
    hw_write(MOD_REG(M_FOLLOW_REL), follow_coef(s, v[P_FOLLOW_REL]));
    if (v[P_SYNC_MODE] != SYNC_NOTE && s->sync_note >= 0) {
        synth_midi(s, 0x80, (uint8_t)s->sync_note, 0);
        s->sync_note = -1;
    }
}

int avk_poll(struct synth *s)
{
    uint32_t e = hw_read(PERIPH_ADDR(9, 0x08));
    if (e == s->sync_edges)
        return 0;
    s->sync_edges = e;
    if (s->p.v[P_DLY_SYNC]) { /* delay time follows the SYNC period */
        uint32_t p = hw_read(PERIPH_ADDR(9, 0x04)), bck = 128u * s->fs.bck_half;
        uint32_t n = (p + bck / 2) / bck;
        if (n && n != s->sync_samples) {
            s->sync_samples = n;
            for (int d = 0; d < AVK_PATCH_SLOTS; d++)
                if (s->dly_slot[d] >= 0)
                    hw_write(SLOT_REG(s->dly_slot[d], SL_PARAM(0)), n);
        }
    }
    if (s->p.v[P_SYNC_MODE] == SYNC_NOTE) {
        /* the same note again retriggers its voice (a quick off/on could fall into one sample) */
        int n = (int)s->p.v[P_SYNC_NOTE];
        if (s->sync_note >= 0 && s->sync_note != n)
            synth_midi(s, 0x80, (uint8_t)s->sync_note, 0);
        s->sync_note = n;
        synth_midi(s, 0x90, (uint8_t)n, 100);
    }
    return 1;
}

void avk_cal_zero(int i)
{
    hw_write(ADC_OFFSET(i), hw_read(ADC_RAW(i)) & 0xFFFu);
}

int avk_cal_ref(int i, int32_t mv)
{
    int32_t d = (int32_t)(hw_read(ADC_RAW(i)) & 0xFFFu) - (int32_t)hw_read(ADC_OFFSET(i));
    if (!d)
        return 0;
    /* x = (d * GAIN) >> 16 = mv / 10000 * 65536 -> GAIN = mv * 2^32 / (10000 * d) */
    hw_write(ADC_GAIN(i), (uint32_t)(((int64_t)mv << 32) / (10000 * (int64_t)d)));
    return 1;
}

uint32_t avk_sync_hz100(const struct synth *s)
{
    uint32_t p = hw_read(PERIPH_ADDR(9, 0x04));
    return p ? (uint32_t)(((uint64_t)s->fs.sys_clk * 100u + p / 2) / p) : 0;
}
