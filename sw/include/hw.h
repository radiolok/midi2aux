/* Memory map and peripheral registers (trs.md 8.2).
 * PRELIMINARY: register layout is fixed at stage 2 together with the RTL. */
#ifndef HW_H
#define HW_H

#include <stdint.h>

#define REG32(addr) (*(volatile uint32_t *)(addr))

#define BSRAM_BASE   0x00000000u
#define PERIPH_BASE  0x10000000u
#define VOICE_BASE   0x20000000u
#define SYNTH_BASE   0x20010000u
#define BUS_BASE     0x30000000u
#define SLOT_BASE    0x30010000u
#define XRAM_BASE    0x40000000u

/* debug UART (BL702) */
#define UART_DATA    REG32(PERIPH_BASE + 0x000)
#define UART_STATUS  REG32(PERIPH_BASE + 0x004)
#define UART_TX_BUSY (1u << 0)

/* GPIO: on-board LEDs */
#define GPIO_OUT     REG32(PERIPH_BASE + 0x100)

/* voice k registers */
#define VOICE_STRIDE 0x40u
#define VOICE_REG(k, off) REG32(VOICE_BASE + (uint32_t)(k) * VOICE_STRIDE + (off))

#endif
