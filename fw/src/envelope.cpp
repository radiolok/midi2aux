#ifdef SINE_ENV

#include "envelope.h"
#include <math.h>

volatile uint8_t msTicks;

static uint16_t atkStep = 32767;
static uint16_t decK;
static uint16_t relK;
static uint8_t sustain;
static int16_t lastPot = -100;
static uint8_t lastTick;

// Per-millisecond multiplier (x/65536) that falls to -40 dB in `ms`.
static uint16_t fallK(float ms) {
	return (uint16_t)(65536.0f * expf(-4.605f / ms));
}

// Called from the main loop; floats are fine here, they run only when the
// pot moves by more than 4 steps.
void envSetPot(uint8_t pot) {
	int16_t d = (int16_t)pot - lastPot;
	if (d > -4 && d < 4)
		return;
	lastPot = pot;

	float atk, dec, rel;
	if (pot < 128) {
		float x = (float)pot / 127.0f;
		atk = 2.0f;
		dec = 50.0f * powf(60.0f, x);		// 50 ms .. 3 s
		rel = dec < 80.0f ? dec : 80.0f;
		sustain = 0;
	} else {
		float y = (float)(pot - 128) / 127.0f;
		atk = 2.0f * powf(500.0f, y);		// 2 ms .. 1 s
		dec = rel = 50.0f * powf(40.0f, y);	// 50 ms .. 2 s
		sustain = 1;
	}
	atkStep = (uint16_t)(65535.0f / atk);
	decK = fallK(dec);
	relK = fallK(rel);
}

// Starts (or retriggers) from the current level; the caller zeroes `level`
// for a fresh voice.
void envStart(Env *e) {
	e->stage = ENV_ATTACK;
}

void envRelease(Env *e) {
	if (e->stage != ENV_IDLE)
		e->stage = ENV_RELEASE;
}

// One 1 ms step. Returns the 8-bit output level; stage becomes ENV_IDLE
// when the sound has died out.
uint8_t envStep(Env *e) {
	switch (e->stage) {
	case ENV_ATTACK: {
		uint32_t l = (uint32_t)e->level + atkStep;
		if (l >= 0xFFFF) {
			l = 0xFFFF;
			e->stage = sustain ? ENV_SUSTAIN : ENV_DECAY;
		}
		e->level = (uint16_t)l;
		break;
	}
	case ENV_SUSTAIN:
		if (!sustain)		// pot moved into the pluck half while held
			e->stage = ENV_DECAY;
		break;
	case ENV_DECAY:
		e->level = ((uint32_t)e->level * decK) >> 16;
		break;
	case ENV_RELEASE:
		e->level = ((uint32_t)e->level * relK) >> 16;
		break;
	}
	if ((e->stage == ENV_DECAY || e->stage == ENV_RELEASE) && e->level < 256) {
		e->level = 0;
		e->stage = ENV_IDLE;
	}
	return e->level >> 8;
}

// Milliseconds since the previous call.
uint8_t envElapsed(void) {
	uint8_t t = msTicks;
	uint8_t n = t - lastTick;
	lastTick = t;
	return n;
}

#endif
