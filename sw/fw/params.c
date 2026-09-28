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

static int msb64(uint64_t x)
{
    int m = 63;
    while (m > 0 && !(x >> m))
        m--;
    return m;
}

uint32_t exp2_frac_q30(uint32_t f_q16)
{
    /* 2^f = e^(f ln 2), f in [0, 1): Taylor series in Horner form, Q30 */
    uint64_t y = ((uint64_t)(f_q16 & 0xFFFFu) * 744261118u) >> 16; /* f ln 2, Q30 */
    uint64_t t = 1u << 30;
    for (uint32_t n = 10; n >= 1; n--)
        t = (1u << 30) + ((y * t / n) >> 30);
    return (uint32_t)t;
}

uint32_t env_coef(const struct fs_info *fs, uint32_t time_us, int attack)
{
    /* c = 1 - e^-x, x = ratio / (time * fs); ratio = -ln(1 - 1/1.3) (attack) or ln(1000), Q24 */
    const uint64_t ratio = attack ? 24601054u : 115892902u;
    uint64_t us_per_sample = (((uint64_t)128000000u * fs->bck_half << 24) + fs->sys_clk / 2) / fs->sys_clk; /* Q24 */
    uint64_t ra = (ratio * us_per_sample + (1u << 23)) >> 24;       /* ratio * 1e6 / fs, Q24 */
    uint64_t x = (ra << 32) / (time_us ? time_us : 1);                /* Q56 */
    /* c = x * g(x), g = 1 - x/2 + x^2/6 - ... (x <= 0.15 for times >= 1 ms) */
    uint64_t x30 = x >> 26, g = 1u << 30;
    for (uint32_t n = 7; n >= 2; n--)
        g = (1u << 30) - ((x30 * g / n) >> 30);
    int e = msb64(x);
    uint64_t cm = ((x >> (e - 30)) * g) >> 30; /* c = cm * 2^(e - 86) */
    int m = msb64(cm);
    int32_t shift = 88 - e - m;
    uint32_t mant = (uint32_t)((cm + (1ull << (m - 17))) >> (m - 16));
    if (shift < 2)
        shift = 2;
    if (shift > 31)
        shift = 31;
    if (mant > 131071u)
        mant = 131071u;
    return ((uint32_t)shift << 17) | mant;
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

uint32_t lfo_inc(const struct fs_info *fs, uint32_t hz_x100)
{
    /* hz / fs * 2^32 = hz_x100 * 2^32 * 128 * half / (100 * sys_clk) */
    uint64_t num = ((uint64_t)hz_x100 << 32) * 128u * fs->bck_half;
    uint64_t den = (uint64_t)fs->sys_clk * 100u;
    return (uint32_t)((num + den / 2) / den);
}
