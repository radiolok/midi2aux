#include "unity_lite.h"

#include "../fw/voice_alloc.c"

/* fake hardware: per-voice idle flag and level */
static int hw_idle[VA_MAX_VOICES];
static uint32_t hw_level[VA_MAX_VOICES];
static int f_idle(void *c, int v) { (void)c; return hw_idle[v]; }
static uint32_t f_level(void *c, int v) { (void)c; return hw_level[v]; }

static struct voice_alloc a;

static void setup(int n)
{
    for (int i = 0; i < VA_MAX_VOICES; i++) {
        hw_idle[i] = 1;
        hw_level[i] = 0;
    }
    va_init(&a, n, (struct va_hw){f_idle, f_level, 0});
}

/* the synth marks voices busy when gated */
static int on(uint8_t note, int *rt)
{
    int v = va_note_on(&a, note, rt);
    hw_idle[v] = 0;
    hw_level[v] = 1000;
    return v;
}

static void test_free_voices_first(void)
{
    int rt;
    setup(4);
    CHECK_EQ(on(60, &rt), 0);
    CHECK_EQ(rt, 0);
    CHECK_EQ(on(64, &rt), 1);
    CHECK_EQ(on(67, &rt), 2);
    CHECK_EQ(va_note_off(&a, 64), 1);
    /* voice 1 is releasing (not idle): voice 3 is free and taken first */
    CHECK_EQ(on(72, &rt), 3);
    CHECK_EQ(rt, 0);
}

static void test_same_note_reuses_voice(void)
{
    int rt;
    setup(4);
    on(60, &rt);
    int v = on(62, &rt);
    CHECK_EQ(on(62, &rt), v); /* pressed again while held */
    CHECK_EQ(rt, 1);
    CHECK_EQ(va_note_off(&a, 62), v);
    CHECK_EQ(on(62, &rt), v); /* while releasing */
    CHECK_EQ(rt, 0);
}

static void test_steal_quietest_releasing(void)
{
    int rt;
    setup(3);
    on(60, &rt);
    on(62, &rt);
    on(64, &rt);
    va_note_off(&a, 60);
    va_note_off(&a, 64);
    hw_level[0] = 500;
    hw_level[2] = 20;
    CHECK_EQ(on(65, &rt), 2);
    CHECK_EQ(rt, 0);
}

static void test_steal_oldest_when_all_held(void)
{
    int rt;
    setup(3);
    on(60, &rt);
    on(62, &rt);
    on(64, &rt);
    CHECK_EQ(on(65, &rt), 0);
    CHECK_EQ(rt, 1);
    CHECK_EQ(on(67, &rt), 1);
    CHECK_EQ(va_note_off(&a, 60), -1); /* stolen note is gone */
}

static void test_idle_after_release_is_free_again(void)
{
    int rt;
    setup(2);
    on(60, &rt);
    on(62, &rt);
    va_note_off(&a, 60);
    hw_idle[0] = 1; /* release finished */
    CHECK_EQ(on(70, &rt), 0);
}

static void test_sustain_pedal(void)
{
    int rt;
    uint32_t m[2];
    setup(4);
    on(60, &rt);
    on(64, &rt);
    va_sustain(&a, 1, m);
    CHECK_EQ(va_note_off(&a, 60), -1);
    CHECK(va_gated(&a, 0));
    on(67, &rt);
    va_sustain(&a, 0, m);
    CHECK_EQ(m[0], 1u);  /* only voice 0 was waiting for the pedal */
    CHECK(!va_gated(&a, 0));
    CHECK(va_gated(&a, 1));
}

static void test_all_off(void)
{
    int rt;
    uint32_t m[2];
    setup(40);
    for (int i = 0; i < 40; i++)
        on((uint8_t)(30 + i), &rt);
    va_note_off(&a, 30);
    va_all_off(&a, m);
    CHECK_EQ(m[0], 0xFFFFFFFEu);
    CHECK_EQ(m[1], 0xFFu);
    CHECK(!va_gated(&a, 5));
}

int main(void)
{
    RUN(test_free_voices_first);
    RUN(test_same_note_reuses_voice);
    RUN(test_steal_quietest_releasing);
    RUN(test_steal_oldest_when_all_held);
    RUN(test_idle_after_release_is_free_again);
    RUN(test_sustain_pedal);
    RUN(test_all_off);
    return TEST_RESULT();
}
