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

/* voice engine (fpga/rtl/voice/voice_engine.sv) */
#define VOICE_REG(k, off)  (VOICE_BASE + (uint32_t)(k) * 0x40u + (off))
#define V_PITCH1           0x00u
#define V_PITCH2           0x04u
#define V_GATE             0x08u /* bit0 gate, bit1 retrigger toggle */
#define V_VEL_AMP          0x0Cu
#define V_CUT_OFS          0x10u
#define V_STATUS           0x14u /* {st2[23:22], st1[21:20], env1[17:0]} */
#define SYNTH_REG(off)     (SYNTH_BASE + (off))
#define S_WAVES            0x00u
#define S_PW               0x04u
#define S_G1               0x08u
#define S_G2               0x0Cu
#define S_GN               0x10u
#define S_CUTOFF           0x14u
#define S_ENV2_DEPTH       0x18u
#define S_RES_Q            0x1Cu
#define S_FMODE            0x20u
#define S_MASTER           0x24u
#define S_A1               0x28u
#define S_D1               0x2Cu
#define S_S1               0x30u
#define S_R1               0x34u
#define S_A2               0x38u
#define S_D2               0x3Cu
#define S_S2               0x40u
#define S_R2               0x44u
#define S_PM               0x48u
#define S_CM               0x4Cu
#define S_AM               0x50u
#define S_INFO             0x54u

/* audio output (Q2.16, 1.0 = machine unit = 65536) */
#define AUDIO_OUT_L        REG32(AUDIO_BASE + 0x00)
#define AUDIO_OUT_R        REG32(AUDIO_BASE + 0x04)
#define Q16_ONE            65536

static inline uint32_t cycles(void) { return TIMER_CYCLES_LO; }

#endif
