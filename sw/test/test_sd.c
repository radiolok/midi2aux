/* sd.c against the SD card model (fpga/sim/models/sd_card_model.h): SDHC and SDSC, errors. */
#include <stdlib.h>

#include "unity_lite.h"

#include "../fw/sd.c"
#include "../../fpga/sim/models/sd_card_model.h"

struct bus {
    struct sd_card card;
    int cs, fast, slow_bytes;
};

static uint8_t bx(void *ctx, uint8_t b)
{
    struct bus *m = ctx;
    if (!m->fast)
        m->slow_bytes++;
    return m->cs ? sd_card_xfer(&m->card, b) : 0xFF;
}

static void bsel(void *ctx, int on)
{
    struct bus *m = ctx;
    if (!on)
        sd_card_deselect(&m->card);
    m->cs = on;
}

static void bspeed(void *ctx, int fast) { ((struct bus *)ctx)->fast = fast; }

static uint8_t img[64 * 512];

static void run(int sdhc)
{
    static struct bus m;
    for (size_t i = 0; i < sizeof img; i++)
        img[i] = (uint8_t)(i * 13 + (i >> 9));
    sd_card_init(&m.card, img, sizeof img, sdhc);
    m.cs = m.fast = m.slow_bytes = 0;
    struct sd s = {bx, bsel, bspeed, &m, 0, 0};
    uint8_t buf[512];
    CHECK_EQ(sd_read(&s, 0, buf), SD_ENOCARD);
    CHECK_EQ(sd_init(&s), SD_OK);
    CHECK_EQ(s.sdhc, sdhc);
    CHECK(m.fast && m.slow_bytes >= 10);
    CHECK_EQ(sd_read(&s, 7, buf), SD_OK);
    CHECK(!memcmp(buf, img + 7 * 512, 512));
    for (int i = 0; i < 512; i++)
        buf[i] = (uint8_t)(255 - i);
    CHECK_EQ(sd_write(&s, 9, buf), SD_OK);
    CHECK(!memcmp(img + 9 * 512, buf, 512));
    CHECK_EQ(img[8 * 512], (uint8_t)(8 * 512 * 13 + 8)); /* neighbours untouched */
    uint8_t rb[512];
    CHECK_EQ(sd_read(&s, 9, rb), SD_OK);
    CHECK(!memcmp(rb, buf, 512));
    CHECK_EQ(sd_read(&s, 64, rb), SD_ECMD); /* past the end */
    CHECK_EQ(m.card.errors, 0);
    CHECK_EQ(m.card.reads, 2);
    CHECK_EQ(m.card.writes, 1);
}

static void test_sdhc(void) { run(1); }
static void test_sdsc(void) { run(0); }

static uint8_t nx(void *ctx, uint8_t b)
{
    (void)ctx;
    (void)b;
    return 0xFF;
}

static void test_no_card(void)
{
    struct bus m = {0};
    struct sd s = {nx, bsel, bspeed, &m, 0, 0};
    CHECK_EQ(sd_init(&s), SD_ENOCARD);
    CHECK_EQ(s.ready, 0);
}

int main(void)
{
    RUN(test_sdhc);
    RUN(test_sdsc);
    RUN(test_no_card);
    return TEST_RESULT();
}
