![](img/midi2aux.jpg)

# MIDI→AUX Converter

Firmware for Arduino Nano (ATmega328P) that converts MIDI Note-On/Off messages into analog audio waveforms. Part of the АВК-6 «Музыкальная пауза» project.

## Hardware

| Pin | Function |
|-----|----------|
| PD0 | MIDI input (RX via optocoupler, 31250 baud) |
| PD2 | Optocoupler enable (active HIGH) |
| PD3 | Audio PWM output (OC2B → RC filter; 160 kHz mono, 62.5 kHz poly) |
| PC0 | Potentiometer (ADC0, 0–5V) |
| PC1 | Button (internal pull-up, mode switch + note off on press) |
| PD4 | LED — Square wave |
| PD5 | LED — Triangle wave |
| PD6 | LED — Sine wave |
| PD7 | LED — Note playing |

## Waveform Modes

| Mode | Waveform | Potentiometer effect |
|------|----------|---------------------|
| 0 | Square | Duty cycle (0–100%) |
| 1 | Triangle | Rise/fall split point (fully left/right = sawtooth) |
| 2 | Sine | None (fixed) |

Short press the button to cycle modes. All notes are silenced on press.

## How It Works

The firmware has two build variants. Both use the same board and pins, and the same
PWM → RC output stage.

### Mono (default)

![Mono mode block diagram](img/arch-mono.svg)

One note at a time; the last pressed note wins. The **sample rate itself is the pitch**:

1. A MIDI byte arrives on PD0 through the optocoupler. `USART_RX_vect` passes it
   straight to `midiParser()`.
2. On Note On, `noteOn()` takes the waveform period for the note from a 12-entry table
   (shifted per octave). It programs Timer0 in CTC mode so that the compare interrupt
   fires **64 times per period of the note**. Prescaler 8 or 64 is chosen by period length.
3. Each `TIMER0_COMPA` interrupt advances `phase` (0…63) and computes one sample of the
   current waveform. Square uses `potValue` as duty, triangle uses it as the split point,
   sine reads a 16-entry quarter-wave table. The sample goes to `OCR2B`.
4. Timer2 runs Fast PWM at 160 kHz (TOP = 99, 100 levels) on OC2B / PD3. The RC low-pass
   turns the duty cycle into an analog voltage on AUX OUT.
5. Note Off for the playing note (or the button, or MIDI Stop 0xFC) stops Timer0 and
   sets `OCR2B = 0`.

The ADC runs free and stores the potentiometer in `potValue`. The Timer1 tick debounces
the button, cycles `waveMode`, and updates the mode LEDs. PD7 is lit while a note plays.

Because Timer0 must interrupt at `note × 64`, high notes are clamped. A sample must not
be shorter than the waveform ISR, so the minimum period is 200 cycles for square and sine
(≈ 1250 Hz) and 350 cycles for triangle (≈ 714 Hz), whose ISR divides.

### Poly (`POLY_VOICES`, prototype)

![Poly mode block diagram](img/arch-poly.svg)

Up to 4 simultaneous notes. Timer0 no longer depends on the note: it **ticks at a fixed
31.25 kHz**, and each voice is a DDS phase accumulator.

1. `USART_RX_vect` only puts the byte into a 16-byte ring buffer (≈ 5 ms of MIDI). The
   main loop wakes after every interrupt, drains the buffer and runs `midiParser()`. That
   keeps the slow work (voice search, voice stealing) out of interrupt context.
2. Note On picks a voice in this order: the same note if it is already playing, then a
   free voice, then the oldest voice (stolen). It sets the voice's 24-bit phase increment
   `inc = f · 2²⁴ / fs`. Note Off releases the voice **by note number**.
3. All voices share one 256-byte `wavetable`. The main loop rebuilds it when the mode or
   the potentiometer changes, so duty and split control still work, and the interrupt
   never divides.
4. Each `TIMER0_COMPA` interrupt first writes the previous sum to `OCR2B`, so the output
   is jitter-free. Then for every active voice it does `acc += inc` and
   `sum += wavetable[acc >> 16]`.
5. Each voice's amplitude is `TOP / N`, so the sum never clips. Timer2 runs 8-bit Fast PWM
   at 62.5 kHz (TOP = 255), which gives 64 levels per voice.

Cost: ≈ 77 + 30·N cycles per sample out of 512 (197 cycles, 38 % CPU for 4 voices).
Pitch is exact (< 0.05 cent). The trade-offs against mono: a single note plays at ¼ of
full scale, high notes alias (fewer samples per period), and PWM ripple rises (62.5 kHz
instead of 160 kHz carrier). Full analysis: [docs/polyphony.md](docs/polyphony.md).

## Building & Upload

```bash
cmake -S . -B build          # avr-gcc from PATH, or -DAVR_TOOLCHAIN_DIR=/path/to/bin
cmake --build build          # build/midi2aux.hex (mono) + build/midi2aux_poly.hex
cmake --build build --target upload_midi2aux       # avrdude, -DAVR_PORT=/dev/ttyUSB0
cmake --build build --target upload_midi2aux_poly
```

Poly options: `-DPOLY_VOICES=1..8`, `-DPOLY_FS=31250`, `-DPOLY_PWM_TOP=255`,
`-DPOLY_ACC_BITS=24`. Prebuilt images are in [fw/bin/](fw/bin/). PlatformIO
(`pio run`) still builds the mono variant.

Remove MIDI jumper before upload — optocoupler gate (PD2) isolates RX.

## Architecture (mono)

Fully interrupt-driven. Main loop does nothing but sleep (`SLEEP_MODE_IDLE`).
In poly mode the main loop also parses MIDI and rebuilds the wavetable.

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

Sample period clamped to ≥ 200 cycles (square, sine) or ≥ 350 cycles (triangle) to prevent ISR cascade on high notes.

### Memory

| Resource | Mono | Poly (4 voices) |
|----------|------|-----------------|
| Flash | 2656 bytes (8.1%) | 3130 bytes (9.6%) |
| RAM | 74 bytes (3.6%) | 827 bytes (40.4%) |

## Project Structure

```
CMakeLists.txt, cmake/avr-gcc.cmake   # CMake build (mono + poly)
platformio.ini                        # PlatformIO build (mono)
fw/src/
├── main.cpp          # init, sleep loop
├── uart.h / uart.cpp # MIDI UART (RX-only; poly: ring buffer)
├── midi.h / midi.cpp # Note period table, MIDI parser, noteOn/noteOff
├── waveform.h / waveform.cpp  # Mono: sine table, waveform ISR, 3 modes
└── poly.h / poly.cpp # Poly: DDS voices, wavetable, voice allocation
fw/bin/               # Prebuilt .hex (mono, poly4)
docs/polyphony.md     # Polyphony analysis and cycle budget
img/                  # Photo, block diagrams (SVG)
tools/isrcycles.py    # ISR cycle count from avr-objdump listing
```

---

*Project created with [KiloCode](https://github.com/Kilo-Org/kilocode) agent, model `deepseek/deepseek-v4-pro`.*
