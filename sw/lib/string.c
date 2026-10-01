#include "lib.h"

void *memcpy(void *d, const void *s, size_t n)
{
    uint8_t *dp = d;
    const uint8_t *sp = s;
    if ((((uintptr_t)dp | (uintptr_t)sp | n) & 3) == 0) {
        uint32_t *dw = d;
        const uint32_t *sw = s;
        for (n >>= 2; n; n--)
            *dw++ = *sw++;
        return d;
    }
    while (n--)
        *dp++ = *sp++;
    return d;
}

void *memmove(void *d, const void *s, size_t n)
{
    uint8_t *dp = d;
    const uint8_t *sp = s;
    if (dp < sp || dp >= sp + n)
        return memcpy(d, s, n);
    while (n--)
        dp[n] = sp[n];
    return d;
}

void *memset(void *d, int c, size_t n)
{
    uint8_t *dp = d;
    while (n--)
        *dp++ = (uint8_t)c;
    return d;
}

int memcmp(const void *a, const void *b, size_t n)
{
    const uint8_t *pa = a, *pb = b;
    for (; n; n--, pa++, pb++)
        if (*pa != *pb)
            return *pa - *pb;
    return 0;
}

size_t strlen(const char *s)
{
    size_t n = 0;
    while (s[n])
        n++;
    return n;
}

int strcmp(const char *a, const char *b)
{
    while (*a && *a == *b)
        a++, b++;
    return (uint8_t)*a - (uint8_t)*b;
}
