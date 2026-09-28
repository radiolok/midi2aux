#include <math.h>
#include <stdlib.h>

#include "unity_lite.h"

#include "../fw/params.c"

static const struct fs_info FS = {99000000u, 16u};

/* values from fpga/model/synthmodel (voice.env_coef, pitch.log2_q16) */
static void test_against_python_model(void)
{
    CHECK_EQ(hz_pitch(&FS, 440), 1652846);
    CHECK_EQ(hz_pitch(&FS, 20), 1360593);
    CHECK_EQ(hz_pitch(&FS, 1000), 1730468);
    CHECK_EQ(hz_pitch(&FS, 16000), 1992612);
    struct {
        uint32_t us;
        int att;
        uint32_t py;
    } c[] = {{1000, 1, 1173895}, {10000, 1, 1543422}, {300000, 0, 1962842}, {10000000, 0, 2613117},
             {2000, 0, 858739}};
    for (unsigned i = 0; i < sizeof c / sizeof c[0]; i++) {
        uint32_t v = env_coef(&FS, c[i].us, c[i].att);
        CHECK_EQ(v >> 17, c[i].py >> 17);                        /* same shift */
        CHECK(labs((long)(v & 0x1FFFF) - (long)(c[i].py & 0x1FFFF)) <= 2); /* mantissa within 2 LSB */
    }
}

static void test_log2(void)
{
    for (uint64_t x = 1; x < (1ull << 40); x = x * 3 + 7) {
        double ref = log2((double)x) * 65536.0;
        CHECK(fabs((double)log2_q16(x) - ref) < 1.001);
    }
    CHECK_EQ(log2_q16(1u << 20), 20u << 16);
}

static void test_notes_and_cents(void)
{
    uint32_t a4 = hz_pitch(&FS, 440);
    CHECK_EQ(note_pitch(a4, 81) - (int32_t)a4, 65536);     /* one octave */
    CHECK(labs((long)(note_pitch(a4, 60) - (int32_t)hz_pitch(&FS, 262))) < 150);
    CHECK_EQ(cents_pitch(1200), 65536);
    CHECK_EQ((int32_t)cents_pitch(-1200), -65536);
}

static void test_exp2(void)
{
    for (uint32_t f = 0; f < 65536; f += 7)
        CHECK(fabs(exp2_frac_q30(f) / 1073741824.0 - exp2(f / 65536.0)) < 1e-8); /* ~10 LSB of Q30 */
}

static void test_env_coef_range(void)
{
    /* every time of the parameter range: within 2 mantissa LSB of the exact value */
    for (uint32_t ms = 1; ms <= 10000; ms += ms < 100 ? 1 : 37)
        for (int att = 0; att < 2; att++) {
            double fs = 99e6 / (128.0 * 16), ratio = att ? -log(1 - 1 / 1.3) : log(1000.0);
            double c = 1 - exp(-ratio / (ms * 1e-3 * fs));
            int shift = (int)ceil(2 - log2(c));
            double mant = c * pow(2, 14 + shift);
            uint32_t v = env_coef(&FS, ms * 1000u, att);
            CHECK_EQ(v >> 17, (uint32_t)shift);
            CHECK(fabs((v & 0x1FFFF) - mant) <= 1.5);
        }
}

static void test_res_and_velocity(void)
{
    CHECK_EQ(res_damping(71), 92304);   /* Q = 0.71 */
    CHECK_EQ(res_damping(1000), 6554);  /* Q = 10 */
    CHECK_EQ(vel_amp(127, 49152), 65536);
    CHECK_EQ(vel_amp(0, 49152), 16384);
    CHECK_EQ(vel_amp(64, 0), 65536);
}

int main(void)
{
    RUN(test_against_python_model);
    RUN(test_log2);
    RUN(test_notes_and_cents);
    RUN(test_exp2);
    RUN(test_env_coef_range);
    RUN(test_res_and_velocity);
    return TEST_RESULT();
}
