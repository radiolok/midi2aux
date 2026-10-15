#ifndef ENVELOPE_H
#define ENVELOPE_H

#include <avr/io.h>

#ifdef SINE_ENV

// Amplitude envelope, stepped once per millisecond from the main loop.
// ENV_MORPH (sine): one potentiometer morphs the character:
//   0..127   pluck / bell: 2 ms attack, decays to silence even while held,
//            decay 50 ms .. 3 s, key release damps within 80 ms
//   128..255 organ -> pad: sustain 100 %, attack 2 ms .. 1 s,
//            release 50 ms .. 2 s
// Decay and release are exponential; times are to -40 dB.
// ENV_GATE (poly square/triangle): 2 ms attack, sustain, 10 ms release, only
// to avoid clicks.
// With POT2_ADC the second pot sets the attack in both shapes, 1 ms .. 1 s
// (in ENV_GATE the release follows the attack, at least 10 ms).

enum { ENV_IDLE, ENV_ATTACK, ENV_DECAY, ENV_SUSTAIN, ENV_RELEASE };

typedef struct {
	uint16_t level;		// 0..65535, output is level >> 8
	uint8_t stage;
} Env;

extern volatile uint8_t msTicks;	// incremented by the 1 ms Timer1 tick

enum { ENV_MORPH, ENV_GATE };

void envConfig(uint8_t shape, uint8_t pot, uint8_t pot2);
void envStart(Env *e);
void envRelease(Env *e);
uint8_t envStep(Env *e);
uint8_t envElapsed(void);
void envPoll(void);			// mono: midi.cpp, poly: poly.cpp

#endif

#endif
