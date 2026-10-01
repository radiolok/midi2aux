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
#define XRAM_BASE    0x40000000u /* external memory window, shared with the delay slots */

#define PERIPH_ADDR(n, off) (PERIPH_BASE + (n) * 0x100u + (off))
#define PERIPH(n, off) REG32(PERIPH_ADDR(n, off))

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
#define SYSINFO_FLAGS      PERIPH(4, 0x24) /* bit0: simulation (shorter delays) */
#define SYSINFO_MEM_WORDS  PERIPH_ADDR(4, 0x28) /* external memory (delay lines), 32-bit words */
#define SYSINFO_NUM_SLOTS  PERIPH_ADDR(4, 0x2C)
#define SYSINFO_ID_AVK6    0x364B5641u

/* 5: SPI master for the flash (and any SPI master block) */
#define SPI_DATA(n)        PERIPH(n, 0x00)
#define SPI_STATUS(n)      PERIPH(n, 0x04)
#define SPI_CS(n)          PERIPH(n, 0x08)
#define SPI_DIV(n)         PERIPH(n, 0x0C)
#define SPI_FLASH          5

/* 6: potentiometers (MCP3208 poller): smoothed 12.4 values, raw 12-bit */
#define POT(k)             PERIPH(6, 4u * (k))
#define POT_RAW(k)         PERIPH(6, 0x20u + 4u * (k))
#define POT_SCANS          PERIPH(6, 0x40)

/* 7: encoders: signed detent counters, buttons */
#define ENC_COUNT(k)       PERIPH(7, 4u * (k))
#define ENC_BUTTONS        PERIPH(7, 0x10)
#define ENC_PRESSED        PERIPH(7, 0x14)

/* 8: ST7789 stream controller */
#define LCD_FIFO           PERIPH(8, 0x00)
#define LCD_STATUS         PERIPH(8, 0x04)
#define LCD_CTRL           PERIPH(8, 0x08) /* {bl[1], rst_n[0]} */
#define LCD_FG             PERIPH(8, 0x0C)
#define LCD_BG             PERIPH(8, 0x10)
#define LCD_DIV            PERIPH(8, 0x14)
#define LCD_ST_BUSY        (1u << 31)
#define LCD_ST_FULL        (1u << 30)
#define LCD_CMD(b)         ((uint32_t)(b))
#define LCD_DATA(b)        (0x100u | (uint32_t)(b))
#define LCD_FILL(n)        ((1u << 30) | (uint32_t)(n))
#define LCD_BITS(n, bits)  ((2u << 30) | ((uint32_t)((n) - 1) << 16) | (uint32_t)(bits))
#define LCD_COLOR_FG(c)    ((3u << 30) | (uint32_t)(c))
#define LCD_COLOR_BG(c)    ((3u << 30) | (1u << 16) | (uint32_t)(c))

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
#define S_ENV_VOICE        0x58u
#define S_HSYNC            0x5Cu /* {osc2, osc1}: hard sync on SYNC edges */
#define S_BLEP             0x60u /* PolyBLEP on saw / square */

/* modulation unit (fpga/rtl/voice/mod_unit.sv) */
#define MOD_BASE           0x20020000u
#define MOD_REG(off)       (MOD_BASE + (off))
#define M_LFO_INC(i)       (0x00u + 8u * (i))
#define M_LFO_CFG(i)       (0x04u + 8u * (i)) /* {sync_reset[4], wave[2:0]} */
#define M_MODWHEEL         0x10u
#define M_AM_BASE          0x14u
#define M_AUX              0x18u
#define M_GATE             0x1Cu
#define M_FOLLOW_SRC       0x20u /* envelope follower: 0 IN1, 1 IN2 */
#define M_FOLLOW_ATK       0x24u /* Q0.16 one-pole coefficients */
#define M_FOLLOW_REL       0x28u
#define M_ROUTE(k)         (0x40u + 8u * (k)) /* {dst[10:8], via[7:4], src[3:0]} */
#define M_DEPTH(k)         (0x44u + 8u * (k))
#define M_LFO_VAL(i)       (0x80u + 4u * (i))
enum { SRC_ZERO, SRC_LFO1, SRC_LFO2, SRC_MODWHEEL, SRC_IN1, SRC_IN2, SRC_SYNC, SRC_ENV, SRC_GATE, SRC_AUX,
       SRC_FOLLOW };
enum { DST_NONE, DST_PM, DST_CM, DST_AM, DST_PW };
enum { LFO_SINE, LFO_TRI, LFO_SAW_UP, LFO_SQUARE, LFO_RANDOM, LFO_SAW_DOWN };

/* 9: SYNC input (after the comparator) */
#define SYNC_LEVEL         PERIPH(9, 0x00)
#define SYNC_PERIOD        PERIPH(9, 0x04) /* sys_clk cycles between the last two rising edges */
#define SYNC_EDGES         PERIPH(9, 0x08)
#define SYNC_FILTER        PERIPH(9, 0x0C)

/* 10: AVK inputs IN1/IN2 (AD7091R): x = sat18(((code - OFFSET) * GAIN) >> 16) */
#define ADC_OFFSET(i)      PERIPH_ADDR(10, 0x00 + 8u * (i))
#define ADC_GAIN(i)        PERIPH_ADDR(10, 0x04 + 8u * (i))
#define ADC_RAW(i)         PERIPH_ADDR(10, 0x10 + 4u * (i))
#define ADC_IN(i)          PERIPH_ADDR(10, 0x18 + 4u * (i))
#define ADC_COUNT          PERIPH_ADDR(10, 0x20)

/* signal bus, slots and output mixer (Q2.16, 1.0 = machine unit = 65536):
 * OUT = softclip(sum GAIN_i * S_i + OUT_DC), OUT2 = softclip(S[OUT2_SEL] * OUT2_GAIN + OUT2_DC) */
#define AUDIO_OUT_L        REG32(AUDIO_BASE + 0x00)
#define AUDIO_OUT_R        REG32(AUDIO_BASE + 0x04)
#define BUS_OUT_DC         (AUDIO_BASE + 0x00)
#define BUS_OUT2_DC        (AUDIO_BASE + 0x04)
#define BUS_OUT2_SEL       (AUDIO_BASE + 0x08)
#define BUS_OUT2_GAIN      (AUDIO_BASE + 0x0C)
#define BUS_GAIN(i)        (AUDIO_BASE + 0x40 + 4u * (i))
#define BUS_VALUE(i)       (AUDIO_BASE + 0x100 + 4u * (i))
enum { BUS_SYNTH, BUS_IN1, BUS_IN2, BUS_LFO1, BUS_LFO2, BUS_SYNC, BUS_ENV, BUS_GATE, BUS_SLOT0 };
#define SLOT_REG(k, off)   (SLOT_BASE + 0x100u * (k) + (off))
#define SL_TYPE            0x00u
#define SL_SEL_A           0x04u
#define SL_SEL_B           0x08u
#define SL_BYPASS          0x0Cu
#define SL_MEM_BASE        0x10u
#define SL_MEM_SIZE        0x14u
#define SL_PARAM(j)        (0x40u + 4u * (j))
enum { SLOT_NONE, SLOT_MATH, SLOT_DELAY, SLOT_CHORUS, SLOT_REVERB };
#define REVERB_WORDS 5934 /* memory a REVERB slot needs */
#define CHORUS_WORDS 2048
/* DELAY: PARAM0 TIME (samples), PARAM1 FB, PARAM2 WET, PARAM3 DRY (Q2.16)
 * CHORUS: PARAM0 BASE, PARAM1 DEPTH (samples), PARAM2 RATE (phase inc), PARAM3 FB, PARAM4 WET, PARAM5 DRY
 * REVERB: PARAM0 ROOM, PARAM1 DAMP (Q0.16), PARAM2 WET, PARAM3 DRY */
enum { MATH_MUL, MATH_DIV, MATH_ABS, MATH_ADD, MATH_SUB, MATH_MIN, MATH_MAX, MATH_MOD, MATH_AXPB };
#define Q16_ONE            65536

static inline uint32_t cycles(void) { return TIMER_CYCLES_LO; }

#endif
