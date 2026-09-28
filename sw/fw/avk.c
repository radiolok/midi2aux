/* AVK link: signal bus gains, effect slots, OUT2, SYNC modes, input calibration.
 * Register access goes through hw_write / hw_read (host-testable). */
#include "hw.h"
#include "synth.h"

static int32_t pct_q16s(int32_t pct) { return pct * 65536 / 100; }

void avk_init(struct synth *s)
{
    s->nslots = 0;
    while (s->nslots < AVK_MAX_SLOTS) {
        uint32_t t = hw_read(SLOT_REG(s->nslots, SL_TYPE));
        if (!t)
            break;
        s->slot_type[s->nslots++] = (uint8_t)t;
    }
    s->sync_edges = hw_read(PERIPH_ADDR(9, 0x08));
    s->sync_note = -1;
}

void avk_apply(struct synth *s)
{
    const int32_t *v = s->p.v;
    hw_write(BUS_GAIN(BUS_IN1), (uint32_t)pct_q16s(v[P_IN1_MIX]));
    hw_write(BUS_GAIN(BUS_IN2), (uint32_t)pct_q16s(v[P_IN2_MIX]));
    for (int k = 0; k < s->nslots; k++) {
        const int32_t *sp = &v[P_SLOT1_OP + k * SLOT_PARAMS]; /* OP, A, B, K */
        int on = sp[0] != 0 && s->slot_type[k] == SLOT_MATH;
        hw_write(SLOT_REG(k, SL_SEL_A), (uint32_t)sp[1]);
        hw_write(SLOT_REG(k, SL_SEL_B), (uint32_t)sp[2]);
        hw_write(SLOT_REG(k, SL_BYPASS), (uint32_t)!on);
        if (on) {
            hw_write(SLOT_REG(k, SL_PARAM(0)), (uint32_t)(sp[0] - 1));
            hw_write(SLOT_REG(k, SL_PARAM(1)), (uint32_t)pct_q16s(sp[3]));
        }
        hw_write(BUS_GAIN(BUS_SLOT0 + k), on ? (uint32_t)pct_q16s(v[P_FX_MIX]) : 0);
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
