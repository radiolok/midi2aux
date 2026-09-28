/* Memory map and peripheral registers (trs.md 8.2, fpga/rtl/synth_core.sv). */
#ifndef HW_H
#define HW_H

#include <stdint.h>

#define REG32(addr) (*(volatile uint32_t *)(addr))

#define RAM_BASE     0x00000000u
#define BOOTROM_BASE 0x00100000u
#define PERIPH_BASE  0x10000000u
#define VOICE_BASE   0x20000000u
#define SYNTH_BASE   0x20010000u
#define AUDIO_BASE   0x30000000u
#define SLOT_BASE    0x30010000u
#define XRAM_BASE    0x40000000u

#define PERIPH(n, off) REG32(PERIPH_BASE + (n) * 0x100u + (off))

/* 0: debug UART */
#define UART_DATA          PERIPH(0, 0x00)
#define UART_STATUS        PERIPH(0, 0x04)
#define UART_RX_VALID      (1u << 31)
#define UART_ST_TX_FULL    (1u << 0)
#define UART_ST_TX_IDLE    (1u << 1)
#define UART_ST_RX_AVAIL   (1u << 2)
#define UART_ST_RX_OVF     (1u << 3)

/* 1: timer */
#define TIMER_CYCLES_LO    PERIPH(1, 0x00)
#define TIMER_CYCLES_HI    PERIPH(1, 0x04)
#define TIMER_SAMPLES      PERIPH(1, 0x08)

/* 2: GPIO */
#define GPIO_OUT           PERIPH(2, 0x00)
#define GPIO_IN            PERIPH(2, 0x04)

/* 3: MIDI event FIFO */
#define MIDI_EVENT         PERIPH(3, 0x00)
#define MIDI_STATUS        PERIPH(3, 0x04)
#define MIDI_CTRL          PERIPH(3, 0x08)
#define MIDI_EV_VALID      (1u << 31)
#define MIDI_ST_OVERFLOW   (1u << 31)

/* 4: system information (read only) */
#define SYSINFO_ID         PERIPH(4, 0x00)
#define SYSINFO_VERSION    PERIPH(4, 0x04)
#define SYSINFO_SYS_CLK    PERIPH(4, 0x08)
#define SYSINFO_BCK_HALF   PERIPH(4, 0x0C)
#define SYSINFO_RAM_BYTES  PERIPH(4, 0x10)
#define SYSINFO_NUM_VOICES PERIPH(4, 0x14)
#define SYSINFO_BOOT_WAIT  PERIPH(4, 0x18)
#define SYSINFO_FW_FLASH   PERIPH(4, 0x1C)
#define SYSINFO_UART_BAUD  PERIPH(4, 0x20)
#define SYSINFO_ID_AVK6    0x364B5641u

/* 5: SPI master for the flash (and any SPI master block) */
#define SPI_DATA(n)        PERIPH(n, 0x00)
#define SPI_STATUS(n)      PERIPH(n, 0x04)
#define SPI_CS(n)          PERIPH(n, 0x08)
#define SPI_DIV(n)         PERIPH(n, 0x0C)
#define SPI_FLASH          5

/* audio output (Q2.16, 1.0 = machine unit = 65536) */
#define AUDIO_OUT_L        REG32(AUDIO_BASE + 0x00)
#define AUDIO_OUT_R        REG32(AUDIO_BASE + 0x04)
#define Q16_ONE            65536

static inline uint32_t cycles(void) { return TIMER_CYCLES_LO; }

#endif
