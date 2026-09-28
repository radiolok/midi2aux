#include "lib.h"

struct out {
    char *buf;
    size_t n, pos;
};

static void put(struct out *o, char c)
{
    if (o->buf) {
        if (o->pos + 1 < o->n)
            o->buf[o->pos] = c;
    } else {
        if (c == '\n')
            uart_putc('\r');
        uart_putc(c);
    }
    o->pos++;
}

static void put_num(struct out *o, uint32_t v, int neg, unsigned base, int upper, int width, char pad, int left)
{
    char tmp[12];
    int i = 0;
    const char *dig = upper ? "0123456789ABCDEF" : "0123456789abcdef";
    do {
        tmp[i++] = dig[v % base];
        v /= base;
    } while (v);
    if (neg)
        tmp[i++] = '-';
    int fill = width > i ? width - i : 0;
    if (neg && pad == '0') { /* sign before zero padding */
        put(o, '-');
        i--;
    }
    if (!left)
        while (fill--)
            put(o, pad);
    while (i)
        put(o, tmp[--i]);
    if (left)
        while (fill-- > 0)
            put(o, ' ');
}

static int vformat(struct out *o, const char *fmt, va_list ap)
{
    for (; *fmt; fmt++) {
        if (*fmt != '%') {
            put(o, *fmt);
            continue;
        }
        fmt++;
        int left = 0, width = 0;
        char pad = ' ';
        if (*fmt == '-') {
            left = 1;
            fmt++;
        }
        if (*fmt == '0') {
            pad = '0';
            fmt++;
        }
        if (*fmt == '*') {
            width = va_arg(ap, int);
            fmt++;
        }
        while (*fmt >= '0' && *fmt <= '9')
            width = width * 10 + (*fmt++ - '0');
        while (*fmt == 'l')
            fmt++;
        switch (*fmt) {
        case 'd':
        case 'i': {
            int32_t v = va_arg(ap, int32_t);
            put_num(o, v < 0 ? -(uint32_t)v : (uint32_t)v, v < 0, 10, 0, width, pad, left);
            break;
        }
        case 'u':
            put_num(o, va_arg(ap, uint32_t), 0, 10, 0, width, pad, left);
            break;
        case 'x':
        case 'X':
            put_num(o, va_arg(ap, uint32_t), 0, 16, *fmt == 'X', width, pad, left);
            break;
        case 'p':
            put(o, '0');
            put(o, 'x');
            put_num(o, (uint32_t)(uintptr_t)va_arg(ap, void *), 0, 16, 0, 8, '0', 0);
            break;
        case 'c':
            put(o, (char)va_arg(ap, int));
            break;
        case 's': {
            const char *s = va_arg(ap, const char *);
            if (!s)
                s = "(null)";
            int len = (int)strlen(s);
            if (!left)
                for (int k = len; k < width; k++)
                    put(o, ' ');
            while (*s)
                put(o, *s++);
            if (left)
                for (int k = len; k < width; k++)
                    put(o, ' ');
            break;
        }
        case '%':
            put(o, '%');
            break;
        case 0:
            return (int)o->pos;
        default:
            put(o, '%');
            put(o, *fmt);
        }
    }
    return (int)o->pos;
}

int xvsnprintf(char *buf, size_t n, const char *fmt, va_list ap)
{
    struct out o = {buf, n, 0};
    int r = vformat(&o, fmt, ap);
    if (n)
        buf[o.pos < n ? o.pos : n - 1] = 0;
    return r;
}

int xsnprintf(char *buf, size_t n, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    int r = xvsnprintf(buf, n, fmt, ap);
    va_end(ap);
    return r;
}

#ifndef HOST_TEST
int xprintf(const char *fmt, ...)
{
    struct out o = {0, 0, 0};
    va_list ap;
    va_start(ap, fmt);
    int r = vformat(&o, fmt, ap);
    va_end(ap);
    return r;
}
#endif
