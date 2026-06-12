# MIDI→AUX Converter

Firmware for Arduino Nano (ATmega328P) that converts MIDI Note-On/Off messages into analog audio waveforms. Part of the АВК-6 «Музыкальная пауза» project.

## Hardware

| Pin | Function |
|-----|----------|
| PD0 | MIDI input (RX via optocoupler) |
| PD2 | Optocoupler enable (active HIGH) |
| PD3 | Audio PWM output (OC2B → RC filter) |
| PC0 | Potentiometer (ADC0, 0–5V) |
| PC1 | Button (internal pull-up, mode switch) |
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

Short press the button to cycle modes.

## Building & Upload

```bash
pio run                 # build
pio run --target upload # build & upload
pio device monitor      # serial monitor (31250 baud)
```

## Architecture

Fully interrupt-driven. Main loop does nothing but sleep.

| Subsystem | Interrupt | Description |
|-----------|-----------|-------------|
| UART | `USART_RX_vect` | MIDI parser called directly, no buffers |
| ADC | `ADC_vect` | Free-running, updates `potValue` every 104 µs |
| Timer0 | `TIMER0_COMPA_vect` | 10 ms tick, button debounce (30 ms) |
| Timer1 | `TIMER1_COMPA_vect` | Waveform generation at note × 64 Hz |
| Timer2 | — | 160 kHz Fast PWM on PD3 (hardware, no ISR) |

### Memory

| Resource | Used | Free |
|----------|------|------|
| Flash | 2524 bytes (8.2%) | 28196 bytes |
| RAM | 74 bytes (3.6%) | 1974 bytes |

## Project Structure

```
platformio.ini
fw/src/
├── main.cpp          # init, sleep loop
├── uart.h / uart.cpp # MIDI UART (RX-only, ISR-driven)
├── midi.h / midi.cpp # Note period table, MIDI parser, noteOn/noteOff
└── waveform.h / waveform.cpp  # Sine table, Timer1 ISR, 4 waveforms
```

---

*Project created with [KiloCode](https://github.com/Kilo-Org/kilocode) agent, model `deepseek/deepseek-v4-pro`.*
