#include "synth.h"

#include "hw.h"

const struct patch default_patch = {
    .wave1 = WAVE_SAW,
    .wave2 = WAVE_SAW,
    .pw_q16 = 32768,
    .detune_cents = 7,
    .osc2_semis = 0,
    .g1 = 32768,
    .g2 = 32768,
    .gn = 0,
    .cutoff_hz = 4000,
    .res_x100 = 100,
    .fmode = FILT_LP,
    .env2_cents = 2400,
    .vel_cut_cents = 1200,
    .vel_amp_depth = 49152,
    .master = 16384,
    .bend_semis = 2,
    .env1 = {.a_us = 5000, .d_us = 300000, .s_q16 = 45875, .r_us = 300000},
    .env2 = {.a_us = 5000, .d_us = 500000, .s_q16 = 19661, .r_us = 300000},
};

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

static void write_env(const struct synth *s, const struct env_patch *e, uint32_t base)
{
    hw_write(SYNTH_REG(base + 0x0), env_coef(&s->fs, e->a_us, 1));
    hw_write(SYNTH_REG(base + 0x4), env_coef(&s->fs, e->d_us, 0));
    hw_write(SYNTH_REG(base + 0x8), e->s_q16);
    hw_write(SYNTH_REG(base + 0xC), env_coef(&s->fs, e->r_us, 0));
}

static uint32_t cutoff(const struct synth *s)
{
    uint32_t c = hz_pitch(&s->fs, s->p.cutoff_hz ? s->p.cutoff_hz : 1);
    return c > PITCH_CUTOFF_MAX ? PITCH_CUTOFF_MAX : c;
}

void synth_apply_patch(struct synth *s)
{
    const struct patch *p = &s->p;
    hw_write(SYNTH_REG(S_WAVES), (uint32_t)(p->wave2 & 3) << 2 | (p->wave1 & 3));
    hw_write(SYNTH_REG(S_PW), p->pw_q16);
    hw_write(SYNTH_REG(S_G1), p->g1);
    hw_write(SYNTH_REG(S_G2), p->g2);
    hw_write(SYNTH_REG(S_GN), p->gn);
    hw_write(SYNTH_REG(S_CUTOFF), cutoff(s));
    hw_write(SYNTH_REG(S_RES_Q), res_damping(p->res_x100));
    hw_write(SYNTH_REG(S_FMODE), p->fmode);
    hw_write(SYNTH_REG(S_ENV2_DEPTH), cents_pitch(p->env2_cents));
    hw_write(SYNTH_REG(S_MASTER), p->master);
    write_env(s, &p->env1, S_A1);
    write_env(s, &p->env2, S_A2);
    hw_write(SYNTH_REG(S_AM), 65536);
    hw_write(SYNTH_REG(S_CM), 0);
}

void synth_init(struct synth *s, int nvoices, struct fs_info fs, const struct patch *p)
{
    s->fs = fs;
    s->nvoices = nvoices;
    s->p = *p;
    s->p_a4 = hz_pitch(&fs, 440);
    s->mod_wheel = 0;
    s->bend = 0;
    va_init(&s->va, nvoices, (struct va_hw){va_idle, va_level, 0});
    for (int v = 0; v < VA_MAX_VOICES; v++)
        s->retrig[v] = 0;
    synth_apply_patch(s);
    hw_write(SYNTH_REG(S_PM), 0);
    for (int v = 0; v < nvoices; v++)
        hw_write(VOICE_REG(v, V_GATE), 0);
}

static void gate(struct synth *s, int v, int on) { hw_write(VOICE_REG(v, V_GATE), (uint32_t)s->retrig[v] << 1 | (on != 0)); }

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
    int rt;
    int v = va_note_on(&s->va, note, &rt);
    int32_t p1 = note_pitch(s->p_a4, note);
    int32_t p2 = p1 + (int32_t)cents_pitch(s->p.detune_cents + 100 * s->p.osc2_semis);
    int32_t cofs = (s->p.vel_cut_cents * ((int32_t)vel - 64)) / 63;
    hw_write(VOICE_REG(v, V_PITCH1), (uint32_t)(p1 < 0 ? 0 : p1));
    hw_write(VOICE_REG(v, V_PITCH2), (uint32_t)(p2 < 0 ? 0 : p2));
    hw_write(VOICE_REG(v, V_VEL_AMP), vel_amp(vel, s->p.vel_amp_depth));
    hw_write(VOICE_REG(v, V_CUT_OFS), cents_pitch(cofs));
    if (rt)
        s->retrig[v] ^= 1;
    gate(s, v, 1);
    return v;
}

static void set_bend(struct synth *s, int16_t bend)
{
    s->bend = bend;
    /* +-8192 -> +-bend_semis semitones: bend * semis * 2^16 / 12 / 8192 */
    int32_t pm = (int32_t)(((int64_t)bend * s->p.bend_semis * 65536) / 98304);
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
            break;
        case 64:
            va_sustain(&s->va, d2 >= 64, m);
            gate_off_mask(s, m);
            break;
        case 121: /* reset all controllers */
            s->mod_wheel = 0;
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
