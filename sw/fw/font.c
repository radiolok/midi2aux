#include "font.h"

const uint8_t *font_glyph(uint32_t cp)
{
    for (const struct font_range *r = font_ranges; r->hi; r++)
        if (cp >= r->lo && cp <= r->hi)
            return font_glyphs[r->first + (cp - r->lo)];
    return font_glyphs['?' - 0x20];
}

uint32_t utf8_next(const char **s)
{
    const uint8_t *p = (const uint8_t *)*s;
    uint32_t c = *p++;
    int extra = 0;
    if (c >= 0xF0) {
        c &= 0x07;
        extra = 3;
    } else if (c >= 0xE0) {
        c &= 0x0F;
        extra = 2;
    } else if (c >= 0xC0) {
        c &= 0x1F;
        extra = 1;
    } else if (c >= 0x80) {
        c = '?';
    }
    while (extra--) {
        if ((*p & 0xC0) != 0x80) {
            c = '?';
            break;
        }
        c = (c << 6) | (*p++ & 0x3F);
    }
    *s = (const char *)p;
    return c;
}

int utf8_len(const char *s)
{
    int n = 0;
    while (*s) {
        utf8_next(&s);
        n++;
    }
    return n;
}
