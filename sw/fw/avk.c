/* AVK link: signal bus gains, effect slots, OUT2, SYNC modes, input calibration.
 * Register access goes through hw_write / hw_read (host-testable). */
#include "hw.h"
#include "synth.h"

static int32_t pct_q16s(int32_t pct) { return pct * 65536 / 100; }

void avk_init(struct synth *s)
{
    uint32_t n = hw_read(SYSINFO_NUM_SLOTS), words = hw_read(SYSINFO_MEM_WORDS);
    int nm = 0, nd = 0, ndly = 0;
    s->nslots = (int)(n > AVK_MAX_SLOTS ? AVK_MAX_SLOTS : n);
    for (int k = 0; k < AVK_PATCH_SLOTS; k++)
        s->math_slot[k] = s->dly_slot[k] = -1;
    for (int k = 0; k < s->nslots; k++) {
        s->slot_type[k] = (uint8_t)hw_read(SLOT_REG(k, SL_TYPE));
        ndly += s->slot_type[k] == SLOT_DELAY;
    }
    /* the external memory is split evenly between the delay slots */
    for (int k = 0; k < s->nslots; k++) {
        if (s->slot_type[k] == SLOT_MATH && nm < AVK_PATCH_SLOTS)
            s->math_slot[nm++] = (int8_t)k;
        if (s->slot_type[k] == SLOT_DELAY) {
            uint32_t size = words / (uint32_t)ndly;
            hw_write(SLOT_REG(k, SL_MEM_BASE), (uint32_t)nd * size);
            hw_write(SLOT_REG(k, SL_MEM_SIZE), size);
            if (nd < AVK_PATCH_SLOTS)
                s->dly_slot[nd] = (int8_t)k;
            nd++;
        }
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
    hw_write(BUS_OUT2_SEL, (uint32_t)v[P_OUT2_SRC]);
    hw_write(BUS_OUT2_GAIN, (uint32_t)pct_q16s(v[P_OUT2_GAIN]));
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
