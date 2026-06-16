#include "midi.h"
#include "waveform.h"

static const uint32_t notes[12] = {
	1956947, 1847042, 1743489, 1646090,
	1553247, 1466074, 1384083, 1306122,
	1233141, 1163636, 1098524, 1036672
};

enum MidiState { MIDI_WAIT_STATUS, MIDI_WAIT_DATA1, MIDI_WAIT_DATA2 };

static uint8_t midiState = MIDI_WAIT_STATUS;
static uint8_t midiStatus = 0;
static uint8_t midiData1 = 0;
static uint8_t midiNote = 0;
volatile uint8_t midiActive = 0;

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
	case 3:  // sine
		minPeriod = 200;
		break;
	case 2:  // ramp
		minPeriod = 240;
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
	midiActive = 1;
}

void noteOff(void) {
	TCCR0B &= ~((1 << CS02) | (1 << CS01) | (1 << CS00));
	TIMSK0 &= ~(1 << OCIE0A);
	OCR2B = 0;
	midiActive = 0;
}

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
				if (midiData1 == midiNote)
					noteOff();
			}
			midiState = MIDI_WAIT_DATA1;
			break;
		default:
			midiState = MIDI_WAIT_STATUS;
			break;
		}
	}
}
