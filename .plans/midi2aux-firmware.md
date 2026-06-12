# MIDI→AUX Converter Firmware Plan

## Overview

Firmware for Arduino Nano (ATmega328P) that converts MIDI Note-On/Off messages into analog audio waveforms. Part of the АВК-6 "Музыкальная пауза" project.

## Hardware Pinout

| Pin   | Function                        |
|-------|---------------------------------|
| PD0   | MIDI input (RX via optocoupler, collector pull-up to +5V) |
| PD1   | Free (TX, unused)               |
| PD3   | Audio PWM output (OC2B) → RC filter → output capacitor |
| PC0   | Potentiometer (ADC0, 0–5V)      |
| PC1   | Button (internal pull-up)       |
| PD4   | LED0 – Square wave              |
| PD5   | LED1 – Triangle wave            |
| PD6   | LED2 – Sawtooth wave            |
| PD7   | LED3 – Sine wave                |

- PD3 = D3 (OC2B) — PWM audio OUT
- PD4–PD7 = D4–D7 — 4 LEDs (as per spec)

## Project Structure

```
C:\home\midi2aux\
├── platformio.ini
├── fw/
│   └── src/
│       ├── main.cpp          # Entry point, setup(), main loop
│       ├── uart.cpp          # Peter Fleury UART (single USART, adapted)
│       ├── uart.h
│       ├── midi.cpp          # Note period table, noteOn/noteOff, MIDI parser
│       ├── midi.h
│       ├── waveform.cpp      # Sine table init, Timer1 ISR, waveform compute
│       └── waveform.h
```

## Architecture

### 1. MIDI Input (USART0 @ 31250 baud)
- Peter Fleury UART library (`ATMEGA_USART0` for ATmega328P)
- Single USART — use `uart_init()`, `uart_getc()`, `uart_available()`
- MIDI parser: collect 3-byte packets (Note On 0x90 / Note Off 0x80)
- Note On velocity>0 → `noteOn(note)`; velocity=0 or Note Off → `noteOff()`
- System Stop (0xFC) → `noteOff()`

### 2. Note→Frequency (from BrainfuckPC reference)
```cpp
uint32_t notes[12] = { 1956947, 1847042, 1743489, 1646090, 1553247, 1466074,
                       1384083, 1306122, 1233141, 1163636, 1098524, 1036672 };

uint16_t getNotePeriod(uint8_t note) {
    uint8_t octave = note / 12;
    uint8_t semi   = note % 12;
    uint32_t fp    = notes[semi] >> octave;
    return (uint16_t)(fp >> 6);  // prescaler=1 → divide by 64
}
```
- This yields `OCR1A = F_CPU / (128 * freq_note) - 1` → Timer1 period for note*64 Hz
- Default octaves: contra (note 24) to third (note 64)

### 3. Timer2 – PWM (160kHz, 100 steps)
- Mode 7: Fast PWM, OCR2A as TOP
- `OCR2A = 99` → `f = 16e6 / 100 = 160kHz`
- Output on PD3 (OC2B), duty cycle = `OCR2B` (0–99)
- `TCCR2A = (1<<COM2B1) | (1<<WGM21) | (1<<WGM20)`
- `TCCR2B = (1<<WGM22) | (1<<CS20)` — prescaler 1

### 4. Timer1 – System Timer (note*64 Hz)
- CTC mode 4, prescaler = 1
- `OCR1A` = period from `getNotePeriod(note)`
- `TIMSK1 = (1<<OCIE1A)`
- ISR fires 64 times per note cycle, computes next PWM value
- Phase counter `phase` (0–63) increments each ISR

### 5. Waveform Generation (4 modes)

Phase counter `phase` (0–63) increments each Timer1 ISR. Pot value `pot` (0–255) from ADC.

| Mode | Pot effect        | Computation |
|------|-------------------|-------------|
| 0 - Square | Duty cycle (0–100%) | `OCR2B = (phase < pot*64/255) ? 99 : 0` |
| 1 - Triangle | Rise/fall split | pot determines split point; linear ramp up then down |
| 2 - Sawtooth | Ramp duration | pot determines ramp duration; linear up then 0 |
| 3 - Sine | **No effect** | 16-entry quarter-wave table lookup |

### 6. Sine Table (16 entries, quarter wave)
- Computed at startup: `sine[i] = sin(i * π / 32) * 49` (0–49)
- Centered at 50 (midpoint of 0–99 PWM range):
  - Q1 (phase 0–15):  `50 + sine[phase]`
  - Q2 (phase 16–31): `50 + sine[31-phase]`
  - Q3 (phase 32–47): `50 - sine[phase-32]`
  - Q4 (phase 48–63): `50 - sine[63-phase]`

### 7. Button & LEDs
- Button on PC1: short press cycles mode 0→1→2→3→0
- Debounce: ~30ms
- LEDs active high on PD4–PD7

### 8. ADC
- PC0 (ADC0), 8-bit via ADCH (ADLAR=1)
- Read in main loop, `volatile uint8_t potValue` (0–255)

### 9. Main Loop Pseudocode
```
loop:
    read ADC → potValue
    if button short press (debounced):
        waveMode = (waveMode+1) % 4
        update LEDs (PD4–PD7)
        wait release
    if uart data available:
        midiParser(uart_getc())
```

### 10. noteOn / noteOff
```
noteOn(note):
    period = getNotePeriod(note)
    OCR1A = period
    TCNT1 = 0
    TCCR1B |= (1<<CS10)  // start timer
    TIMSK1 |= (1<<OCIE1A)

noteOff():
    TCCR1B &= ~((1<<CS12)|(1<<CS11)|(1<<CS10))  // stop timer
    TIMSK1 &= ~(1<<OCIE1A)
    OCR2B = 0  // silence PWM
```

## Implementation Order

1. Create `platformio.ini` (bare AVR-GCC, board nanoatmega328)
2. Copy & adapt `uart.h`/`uart.cpp` — strip uart2/uart3, keep single USART
3. Create `midi.h`/`midi.cpp` — note table, period calc, MIDI parser state machine
4. Create `waveform.h`/`waveform.cpp` — sine table init, Timer1 ISR, 4 waveforms
5. Create `main.cpp` — timer init, GPIO, ADC, main loop
6. Build: `pio run`
7. Upload: `pio run --target upload`
