#include "synth.h"

#include "hw.h"

static uint32_t pct_q16(int32_t pct) { return (uint32_t)((pct * 65536 + 50) / 100); }

static int va_idle(void *ctx, int v)
{
    (void)ctx;
    return ((hw_read(VOICE_REG(v, V_STATUS)) >> 20) & 3u) == 0;
}

static uint32_t va_level(void *ctx, int v)
{
    (void)ctx;
    return hw_read(VOICE_REG(v, V_STATUS)) & 0x3FFFFu;
}

static void write_env(const struct synth *s, int a, uint32_t base)
{
    const int32_t *v = &s->p.v[a]; /* A, D, S, R consecutive */
    hw_write(SYNTH_REG(base + 0x0), env_coef(&s->fs, (uint32_t)v[0] * 1000u, 1));
    hw_write(SYNTH_REG(base + 0x4), env_coef(&s->fs, (uint32_t)v[1] * 1000u, 0));
    hw_write(SYNTH_REG(base + 0x8), (uint32_t)((v[2] * 65535 + 50) / 100));
    hw_write(SYNTH_REG(base + 0xC), env_coef(&s->fs, (uint32_t)v[3] * 1000u, 0));
}

void synth_set_route(struct synth *s, int k, struct mod_route r)
{
    s->routes[k] = r;
    hw_write(MOD_REG(M_ROUTE(k)), (uint32_t)(r.dst & 7) << 8 | (uint32_t)(r.via & 15) << 4 | (r.src & 15));
    hw_write(MOD_REG(M_DEPTH(k)), (uint32_t)r.depth & 0xFFFFFFu);
}

void synth_apply_patch(struct synth *s)
{
    const int32_t *v = s->p.v;
    uint32_t c = hz_pitch(&s->fs, (uint32_t)v[P_CUTOFF]);
    hw_write(SYNTH_REG(S_WAVES), (uint32_t)(v[P_WAVE2] & 3) << 2 | (v[P_WAVE1] & 3));
    hw_write(SYNTH_REG(S_PW), pct_q16(v[P_PW]));
    hw_write(SYNTH_REG(S_G1), pct_q16(v[P_MIX1]));
    hw_write(SYNTH_REG(S_G2), pct_q16(v[P_MIX2]));
    hw_write(SYNTH_REG(S_GN), pct_q16(v[P_NOISE]));
    hw_write(SYNTH_REG(S_CUTOFF), c > PITCH_CUTOFF_MAX ? PITCH_CUTOFF_MAX : c);
    hw_write(SYNTH_REG(S_RES_Q), res_damping((uint32_t)v[P_RES]));
    hw_write(SYNTH_REG(S_FMODE), (uint32_t)v[P_FMODE]);
    hw_write(SYNTH_REG(S_ENV2_DEPTH), cents_pitch(v[P_ENV2_AMT]));
    hw_write(SYNTH_REG(S_MASTER), pct_q16(v[P_MASTER]));
    write_env(s, P_A1, S_A1);
    write_env(s, P_A2, S_A2);
    hw_write(SYNTH_REG(S_AM), 65536);
    hw_write(SYNTH_REG(S_CM), 0);
    hw_write(MOD_REG(M_LFO_INC(0)), lfo_inc(&s->fs, (uint32_t)v[P_LFO1_RATE]));
    hw_write(MOD_REG(M_LFO_CFG(0)), (uint32_t)v[P_LFO1_WAVE]);
    hw_write(MOD_REG(M_LFO_INC(1)), lfo_inc(&s->fs, (uint32_t)v[P_LFO2_RATE]));
    hw_write(MOD_REG(M_LFO_CFG(1)), (uint32_t)v[P_LFO2_WAVE]);
    synth_set_route(s, 0, (struct mod_route){SRC_LFO1, SRC_MODWHEEL, DST_PM, (int32_t)cents_pitch(v[P_VIBRATO])});
}

void synth_set_param(struct synth *s, int id, int32_t value)
{
    s->p.v[id] = param_clamp(id, value);
    synth_apply_patch(s);
}

static void update_gate(struct synth *s)
{
    int any = 0;
    for (int v = 0; v < s->nvoices; v++)
        any |= va_gated(&s->va, v);
    hw_write(MOD_REG(M_GATE), (uint32_t)any);
}

static void gate(struct synth *s, int v, int on)
{
    hw_write(VOICE_REG(v, V_GATE), (uint32_t)s->retrig[v] << 1 | (on != 0));
    update_gate(s);
}

void synth_init(struct synth *s, int nvoices, struct fs_info fs)
{
    s->fs = fs;
    s->nvoices = nvoices;
    patch_defaults(&s->p);
    s->p_a4 = hz_pitch(&fs, 440);
    s->mod_wheel = 0;
    s->bend = 0;
    va_init(&s->va, nvoices, (struct va_hw){va_idle, va_level, 0});
    for (int v = 0; v < VA_MAX_VOICES; v++)
        s->retrig[v] = 0;
    for (int k = 0; k < MOD_ROUTES; k++)
        synth_set_route(s, k, (struct mod_route){0, 0, DST_NONE, 0});
    hw_write(MOD_REG(M_MODWHEEL), 0);
    hw_write(MOD_REG(M_AM_BASE), 65536);
    synth_apply_patch(s);
    hw_write(SYNTH_REG(S_PM), 0);
    for (int v = 0; v < nvoices; v++)
        hw_write(VOICE_REG(v, V_GATE), 0);
    update_gate(s);
}

static void gate_off_mask(struct synth *s, const uint32_t m[2])
{
    for (int v = 0; v < s->nvoices; v++)
        if (m[v >> 5] & (1u << (v & 31)))
            gate(s, v, 0);
}

void synth_all_off(struct synth *s)
{
    uint32_t m[2];
    va_all_off(&s->va, m);
    gate_off_mask(s, m);
}

static int note_on(struct synth *s, uint8_t note, uint8_t vel)
{
    const int32_t *pv = s->p.v;
    int rt;
    int v = va_note_on(&s->va, note, &rt);
    int32_t p1 = note_pitch(s->p_a4, note);
    int32_t p2 = p1 + (int32_t)cents_pitch(pv[P_DETUNE] + 100 * pv[P_OSC2_SEMI]);
    int32_t cofs = (pv[P_VEL_CUT] * ((int32_t)vel - 64)) / 63;
    hw_write(VOICE_REG(v, V_PITCH1), (uint32_t)(p1 < 0 ? 0 : p1));
    hw_write(VOICE_REG(v, V_PITCH2), (uint32_t)(p2 < 0 ? 0 : p2));
    hw_write(VOICE_REG(v, V_VEL_AMP), vel_amp(vel, pct_q16(pv[P_VEL_AMP])));
    hw_write(VOICE_REG(v, V_CUT_OFS), cents_pitch(cofs));
    if (rt)
        s->retrig[v] ^= 1;
    hw_write(SYNTH_REG(S_ENV_VOICE), (uint32_t)v);
    gate(s, v, 1);
    return v;
}

static void set_bend(struct synth *s, int16_t bend)
{
    s->bend = bend;
    /* +-8192 -> +-range semitones: bend * range * 2^16 / 12 / 8192 */
    int32_t pm = (int32_t)(((int64_t)bend * s->p.v[P_BEND] * 65536) / 98304);
    hw_write(SYNTH_REG(S_PM), (uint32_t)pm);
}

int synth_midi(struct synth *s, uint8_t st, uint8_t d1, uint8_t d2)
{
    uint32_t m[2];
    switch (st & 0xF0) {
    case 0x90:
        return note_on(s, d1, d2);
    case 0x80: {
        int v = va_note_off(&s->va, d1);
        if (v >= 0)
            gate(s, v, 0);
        return v;
    }
    case 0xB0:
        switch (d1) {
        case 1:
            s->mod_wheel = d2;
            hw_write(MOD_REG(M_MODWHEEL), ((uint32_t)d2 << 16) / 127u);
            break;
        case 64:
            va_sustain(&s->va, d2 >= 64, m);
            gate_off_mask(s, m);
            update_gate(s);
            break;
        case 121: /* reset all controllers */
            s->mod_wheel = 0;
            hw_write(MOD_REG(M_MODWHEEL), 0);
            set_bend(s, 0);
            va_sustain(&s->va, 0, m);
            gate_off_mask(s, m);
            break;
        case 120: /* all sound off */
        case 123: /* all notes off */
            synth_all_off(s);
            break;
        default:
            break;
        }
        return -1;
    case 0xE0:
        set_bend(s, (int16_t)(((int)d2 << 7 | d1) - 8192));
        return -1;
    case 0xF0:
        if (st == 0xFC)
            synth_all_off(s);
        return -1;
    default:
        return -1;
    }
}
