#ifndef ENVELOPE_H
#define ENVELOPE_H

#include <avr/io.h>

#ifdef SINE_ENV

// Sine-mode amplitude envelope, stepped once per millisecond from the main loop.
// One potentiometer morphs the character:
//   0..127   pluck / bell: 2 ms attack, decays to silence even while held,
//            decay 50 ms .. 3 s, key release damps within 80 ms
//   128..255 organ -> pad: sustain 100 %, attack 2 ms .. 1 s,
//            release 50 ms .. 2 s
// Decay and release are exponential; times are to -40 dB.

enum { ENV_IDLE, ENV_ATTACK, ENV_DECAY, ENV_SUSTAIN, ENV_RELEASE };

typedef struct {
	uint16_t level;		// 0..65535, output is level >> 8
	uint8_t stage;
} Env;

extern volatile uint8_t msTicks;	// incremented by the 1 ms Timer1 tick

void envSetPot(uint8_t pot);
void envStart(Env *e);
void envRelease(Env *e);
uint8_t envStep(Env *e);
uint8_t envElapsed(void);
void envPoll(void);			// mono: midi.cpp, poly: poly.cpp

#endif

#endif
