# MIDI→AUX Converter

Firmware for Arduino Nano (ATmega328P) that converts MIDI Note-On/Off messages into analog audio waveforms. Part of the АВК-6 «Музыкальная пауза» project.

## Hardware

| Pin | Function |
|-----|----------|
| PD0 | MIDI input (RX via optocoupler, 31250 baud) |
| PD2 | Optocoupler enable (active HIGH) |
| PD3 | Audio PWM output (OC2B → RC filter, 160 kHz) |
| PC0 | Potentiometer (ADC0, 0–5V) |
| PC1 | Button (internal pull-up, mode switch + note off on press) |
| PD4 | LED — Square wave |
| PD5 | LED — Triangle wave |
| PD6 | LED — Sawtooth wave |
| PD7 | LED — Sine wave |

## Waveform Modes

| Mode | Waveform | Potentiometer effect |
|------|----------|---------------------|
| 0 | Square | Duty cycle (0–100%) |
| 1 | Triangle | Rise/fall split point |
| 2 | Sawtooth | Ramp duration |
| 3 | Sine | None (fixed) |

Short press the button to cycle modes. Note is silenced on press.

## Building & Upload

```bash
pio run                 # build
pio run --target upload # build & upload
```

Remove MIDI jumper before upload — optocoupler gate (PD2) isolates RX.

## Architecture

Fully interrupt-driven. Main loop does nothing but sleep (`SLEEP_MODE_IDLE`).

| Subsystem | Timer | Interrupt | Priority | Description |
|-----------|-------|-----------|----------|-------------|
| Button | Timer1 | `TIMER1_COMPA_vect` | **High** | 10 ms tick, debounce 30 ms, calls `noteOff()` on press |
| Waveform | Timer0 | `TIMER0_COMPA_vect` | Low | Generates PWM sample at note × 64 Hz |
| Audio PWM | Timer2 | — | — | 160 kHz Fast PWM on PD3, OCR2B updated by waveform ISR |
| ADC | — | `ADC_vect` | — | Free-running, updates `potValue` every 104 µs |
| MIDI | — | `USART_RX_vect` | — | Calls `midiParser()` directly, no buffers |

### Timer0 Prescaler

| Period | Prescaler | OCR0A range |
|--------|-----------|-------------|
| < 2040 | 8 | 62–254 |
| ≥ 2040 | 64 | 32–238 |

OCR0A clamped to ≥ 350 (44 µs period at prescaler 8) to prevent ISR cascade on high notes.

### Memory

| Resource | Used | Free |
|----------|------|------|
| Flash | 2586 bytes (8.4%) | 28134 bytes |
| RAM | 74 bytes (3.6%) | 1974 bytes |

## Project Structure

```
platformio.ini
fw/src/
├── main.cpp          # init, sleep loop
├── uart.h / uart.cpp # MIDI UART (RX-only, ISR-driven)
├── midi.h / midi.cpp # Note period table, MIDI parser, noteOn/noteOff
└── waveform.h / waveform.cpp  # Sine table, waveform ISR, 4 modes
```

---

*Project created with [KiloCode](https://github.com/Kilo-Org/kilocode) agent, model `deepseek/deepseek-v4-pro`.*
