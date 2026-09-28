#include "hw.h"
#include "lib.h"

void uart_putc(char c)
{
    while (UART_STATUS & UART_ST_TX_FULL)
        ;
    UART_DATA = (uint8_t)c;
}

void uart_puts(const char *s)
{
    while (*s) {
        if (*s == '\n')
            uart_putc('\r');
        uart_putc(*s++);
    }
}

int uart_getc_nb(void)
{
    uint32_t v = UART_DATA;
    return (v & UART_RX_VALID) ? (int)(v & 0xFF) : -1;
}

int uart_getc_timeout(uint32_t n)
{
    uint32_t t0 = cycles();
    do {
        int c = uart_getc_nb();
        if (c >= 0)
            return c;
    } while (cycles() - t0 < n);
    return -1;
}

void uart_flush(void)
{
    while (!(UART_STATUS & UART_ST_TX_IDLE))
        ;
}
