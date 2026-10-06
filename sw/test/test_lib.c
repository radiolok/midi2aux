/* Host tests of the freestanding runtime (sw/lib). */
#include "unity_lite.h"

#include "../lib/crc32.c"
#include "../lib/xprintf.c"

void uart_putc(char c) { (void)c; }

static char buf[64];

static void test_printf_basic(void)
{
    xsnprintf(buf, sizeof buf, "%d %u %x %X %c %s %%", -42, 42u, 0xbeefu, 0xbeefu, 'z', "str");
    CHECK_STR(buf, "-42 42 beef BEEF z str %");
    xsnprintf(buf, sizeof buf, "[%5d][%-5d][%05d][%02x][%-4s][%4s]", 42, 42, -42, 5u, "ab", "ab");
    CHECK_STR(buf, "[   42][42   ][-0042][05][ab  ][  ab]");
    xsnprintf(buf, sizeof buf, "%d %d %u", 0, (int)0x80000000, 0xFFFFFFFFu);
    CHECK_STR(buf, "0 -2147483648 4294967295");
    const char *volatile nul = 0; /* not constant-folded: gcc warns on a literal NULL for %s */
    xsnprintf(buf, sizeof buf, "%s %lu", nul, 7ul);
    CHECK_STR(buf, "(null) 7");
    xsnprintf(buf, sizeof buf, "[%*s][%*d]", 3, "a", 4, 12);
    CHECK_STR(buf, "[  a][  12]");
}

static void test_printf_truncation(void)
{
    int n = xsnprintf(buf, 6, "%s", "0123456789");
    CHECK_EQ(n, 10);
    CHECK_STR(buf, "01234");
}

static void test_crc32(void)
{
    CHECK_EQ(crc32("123456789", 9), 0xCBF43926u); /* standard check value */
    CHECK_EQ(crc32("", 0), 0);
    uint32_t c = crc32_update(0, "1234", 4);
    CHECK_EQ(crc32_update(c, "56789", 5), 0xCBF43926u);
}

int main(void)
{
    RUN(test_printf_basic);
    RUN(test_printf_truncation);
    RUN(test_crc32);
    return TEST_RESULT();
}
