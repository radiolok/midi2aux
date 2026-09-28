/* Stage 0 firmware stub: proves the RISC-V toolchain and the linker script.
 * Real drivers appear at stage 2 (PicoRV32 + bus). */
#include "hw.h"

static void uart_putc(char c)
{
    while (UART_STATUS & UART_TX_BUSY)
        ;
    UART_DATA = (uint8_t)c;
}

static void uart_puts(const char *s)
{
    while (*s)
        uart_putc(*s++);
}

static void delay(uint32_t n)
{
    while (n--)
        __asm__ volatile("nop");
}

static uint32_t blink_count;

int main(void)
{
    uart_puts("AVK-6 synth: firmware stub\r\n");
    for (;;) {
        GPIO_OUT = ++blink_count & 1u;
        delay(1000000);
    }
}
