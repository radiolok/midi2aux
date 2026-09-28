#include "params.h"

uint32_t log2_q16(uint64_t x)
{
    if (!x)
        return 0;
    int msb = 63;
    while (!(x >> msb))
        msb--;
    /* y in Q1.30 */
    uint64_t y = msb >= 30 ? x >> (msb - 30) : x << (30 - msb);
    uint32_t r = (uint32_t)msb;
    for (int i = 0; i < 16; i++) {
        y = (y * y) >> 30;
        r <<= 1;
        if (y >= (2ull << 30)) {
            y >>= 1;
            r |= 1;
        }
    }
    return r;
}

uint32_t hz_pitch(const struct fs_info *fs, uint32_t hz)
{
    /* inc = round(hz * 2^32 / fs) = round(hz * 2^32 * 128 * half / sys_clk) */
    uint64_t num = ((uint64_t)hz << 32) * 128u * fs->bck_half;
    return log2_q16((num + fs->sys_clk / 2) / fs->sys_clk);
}

int32_t note_pitch(uint32_t p_a4, int note)
{
    int32_t d = (note - 69) * 65536; /* semitone = 2^16 / 12, rounded to nearest */
    return (int32_t)p_a4 + (d >= 0 ? (d + 6) / 12 : (d - 6) / 12);
}

uint32_t cents_pitch(int32_t cents)
{
    /* 2^16 / 1200 = 54.613 per cent, rounded */
    return (uint32_t)(((int64_t)cents * 3579139 + 32768) >> 16);
}

float fexp_neg(float x)
{
    if (x > 80.0f)
        return 0.0f;
    int k = (int)(x * 1.44269504f);
    float r = (x - (float)k * 0.693145752f) - (float)k * 1.42860677e-6f; /* ln 2 split (Cody-Waite) */
    float t = 1.0f;
    for (int n = 10; n >= 1; n--) /* Horner form of the Taylor series of e^-r */
        t = 1.0f - r / (float)n * t;
    while (k-- > 0)
        t *= 0.5f;
    return t;
}

uint32_t env_coef(const struct fs_info *fs, uint32_t time_us, int attack)
{
    const float ratio = attack ? 1.46633707f : 6.90775528f; /* -ln(1 - 1/1.3), ln(1000) */
    float fsr = (float)fs->sys_clk / (128.0f * (float)fs->bck_half);
    float tau = (float)(time_us ? time_us : 1) * 1e-6f / ratio;
    float x = 1.0f / (tau * fsr);
    float c = x < 1e-3f ? x * (1.0f - x * 0.5f * (1.0f - x / 3.0f)) : 1.0f - fexp_neg(x);
    if (c > 1.0f)
        c = 1.0f;
    uint32_t shift = 2;
    float scale = 65536.0f; /* 2^(14 + shift) */
    while (shift < 31 && c * scale < 65536.0f) {
        shift++;
        scale *= 2.0f;
    }
    uint32_t mant = (uint32_t)(c * scale + 0.5f);
    if (mant > 131071u)
        mant = 131071u;
    return (shift << 17) | mant;
}

uint32_t res_damping(uint32_t q_x100)
{
    if (q_x100 < 50)
        q_x100 = 50;
    return (uint32_t)((6553600u + q_x100 / 2) / q_x100);
}

uint32_t vel_amp(uint8_t vel, uint32_t depth_q16)
{
    uint32_t v2 = (uint32_t)vel * vel * 65536u / (127u * 127u); /* (v/127)^2, Q16 */
    return 65536u - (uint32_t)(((uint64_t)depth_q16 * (65536u - v2)) >> 16);
}
