/* Non-blocking log ring buffer: printing never stalls the MIDI -> sound path. */
#include "lib.h"

#define LOG_SIZE 512u /* power of two */

static char ring[LOG_SIZE];
static uint32_t head, tail; /* head: write, tail: read */

static void put(char c)
{
    if (head - tail < LOG_SIZE)
        ring[head++ & (LOG_SIZE - 1)] = c;
}

void log_printf(const char *fmt, ...)
{
    char buf[128];
    va_list ap;
    va_start(ap, fmt);
    xvsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    for (const char *p = buf; *p; p++) {
        if (*p == '\n')
            put('\r');
        put(*p);
    }
}

void log_poll(void)
{
    while (tail != head && uart_try_putc(ring[tail & (LOG_SIZE - 1)]))
        tail++;
}

void log_flush(void)
{
    while (tail != head)
        log_poll();
    uart_flush();
}
