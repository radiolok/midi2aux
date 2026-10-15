#include "midi.h"
#include "waveform.h"
#include "poly.h"
#include "envelope.h"
#include <util/atomic.h>

#ifndef POLY_VOICES
static const uint32_t notes[12] = {
	1956947, 1847042, 1743489, 1646090,
	1553247, 1466074, 1384083, 1306122,
	1233141, 1163636, 1098524, 1036672
};
#endif

enum MidiState { MIDI_WAIT_STATUS, MIDI_WAIT_DATA1, MIDI_WAIT_DATA2 };

static uint8_t midiState = MIDI_WAIT_STATUS;
static uint8_t midiStatus = 0;
static uint8_t midiData1 = 0;
static uint8_t midiNote = 0;
volatile uint8_t midiActive = 0;

#ifndef POLY_VOICES
#ifdef SINE_ENV
static Env monoEnv;
#endif

uint16_t getNotePeriod(uint8_t note) {
	uint8_t octave = note / 12;
	uint8_t semi   = note % 12;
	uint32_t fp    = notes[semi] >> octave;
	return (uint16_t)(fp >> 6);
}

void noteOn(uint8_t note) {
	uint16_t period = getNotePeriod(note);
	uint16_t minPeriod;
	switch (waveMode) {
	case 0:  // square
	case 2:  // sine
		minPeriod = 200;
		break;
	case 1:  // triangle
	default:
		minPeriod = 350;
		break;
	}
	if (period < minPeriod) period = minPeriod;

	TCNT0 = 0;
	if (period < 2040) {
		OCR0A  = (uint8_t)(period / 8);
		TCCR0B = (1 << CS01);
	} else {
		OCR0A  = (uint8_t)(period / 64);
		TCCR0B = (1 << CS01) | (1 << CS00);
	}
	TIMSK0 |= (1 << OCIE0A);
#ifdef SINE_ENV
	if (waveMode == 2) {
		if (!midiActive)
			monoEnv.level = 0;
		envStart(&monoEnv);
		envOut = monoEnv.level >> 8;
	}
#endif
	PORTD |= (1 << 7);
	midiActive = 1;
}

void noteOff(void) {
	TCCR0B &= ~((1 << CS02) | (1 << CS01) | (1 << CS00));
	TIMSK0 &= ~(1 << OCIE0A);
#ifdef SINE_ENV
	OCR2B = (waveMode == 2) ? 50 : 0;	// sine idles at mid-scale: no click
#else
	OCR2B = 0;
#endif
	PORTD &= ~(1 << 7);
	midiActive = 0;
}

#ifdef SINE_ENV
// Main loop: 1 ms envelope steps; a finished release stops the note.
void envPoll(void) {
	uint8_t mode = waveMode;
	if (mode == 2)
		envConfig(ENV_MORPH, potValue, pot2Value);
	for (uint8_t n = envElapsed(); n; n--) {
		ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
			if (midiActive && mode == 2) {
				envOut = envStep(&monoEnv);
				if (monoEnv.stage == ENV_IDLE)
					noteOff();
			}
		}
	}
	ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
		if (!midiActive)	// idle level follows mode changes by the button
			OCR2B = (waveMode == 2) ? 50 : 0;
	}
}

static void noteRelease(uint8_t note) {
	if (note != midiNote)
		return;
	if (waveMode == 2)
		envRelease(&monoEnv);
	else
		noteOff();
}
#endif
#endif

void midiParser(uint8_t byte) {
	if (byte & 0x80) {
		if (byte == 0xFC) {
			noteOff();
			return;
		}
		if (byte >= 0xF8) return;

		midiStatus = byte;
		midiState = MIDI_WAIT_DATA1;
	} else {
		switch (midiState) {
		case MIDI_WAIT_DATA1:
			midiData1 = byte;
			midiState = MIDI_WAIT_DATA2;
			break;
		case MIDI_WAIT_DATA2:
			if ((midiStatus & 0xF0) == 0x90 && byte > 0) {
				midiNote = midiData1;
				noteOn(midiNote);
			} else if ((midiStatus & 0xF0) == 0x80
			           || ((midiStatus & 0xF0) == 0x90 && byte == 0)) {
#ifdef POLY_VOICES
				noteRelease(midiData1);
#elif defined(SINE_ENV)
				noteRelease(midiData1);
#else
				if (midiData1 == midiNote)
					noteOff();
#endif
			}
			midiState = MIDI_WAIT_DATA1;
			break;
		default:
			midiState = MIDI_WAIT_STATUS;
			break;
		}
	}
}
