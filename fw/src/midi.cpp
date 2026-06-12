#include "midi.h"
#include <avr/pgmspace.h>
#include "uart.h"

static const uint32_t notes[12] = {
	1956947, 1847042, 1743489, 1646090,
	1553247, 1466074, 1384083, 1306122,
	1233141, 1163636, 1098524, 1036672
};

static const char notename_letter[12] PROGMEM = { 'C','C','D','D','E','F','F','G','G','A','A','B' };
static const char notename_sign[12]  PROGMEM = { ' ','#',' ','#',' ',' ','#',' ','#',' ','#',' ' };

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
	OCR1A  = period;
	TCNT1  = 0;
	TCCR1B |= (1 << CS10);
	TIMSK1 |= (1 << OCIE1A);
	midiActive = 1;
}

void noteOff(void) {
	TCCR1B &= ~((1 << CS12) | (1 << CS11) | (1 << CS10));
	TIMSK1 &= ~(1 << OCIE1A);
	OCR2B = 0;
	midiActive = 0;
}

static void puthex(uint8_t val) {
	uint8_t hi = (val >> 4) & 0x0F;
	uint8_t lo = val & 0x0F;
	uart_putc(hi < 10 ? '0' + hi : 'A' + hi - 10);
	uart_putc(lo < 10 ? '0' + lo : 'A' + lo - 10);
}

static void crlf(void) {
	uart_putc('\r');
	uart_putc('\n');
}

static void printNote(uint8_t note) {
	uint8_t semi = note % 12;
	uint8_t oct  = note / 12;
	uart_putc(pgm_read_byte(&notename_letter[semi]));
	char sign = pgm_read_byte(&notename_sign[semi]);
	if (sign != ' ') uart_putc(sign);
	if (oct < 10) {
		uart_putc('0' + oct);
	} else {
		uart_putc('0' + oct / 10);
		uart_putc('0' + oct % 10);
	}
}

void midiParser(uint8_t byte) {
	puthex(byte);
	uart_putc(' ');

	if (byte & 0x80) {
		if (byte == 0xFC) {
			crlf();
			noteOff();
			return;
		}
		if (byte >= 0xF8) {
			crlf();
			return;
		}

		midiStatus = byte;
		midiState = MIDI_WAIT_DATA1;
	} else {
		switch (midiState) {
		case MIDI_WAIT_DATA1:
			midiData1 = byte;
			midiState = MIDI_WAIT_DATA2;
			break;
		case MIDI_WAIT_DATA2: {
			uint8_t vel = byte;
			if ((midiStatus & 0xF0) == 0x90 && vel > 0) {
				midiNote = midiData1;
				noteOn(midiNote);
				uart_puts_P("ON  ch=");
				uart_putc('0' + (midiStatus & 0x0F));
				uart_puts_P(" note=");
				printNote(midiNote);
				uart_puts_P(" vel=");
				puthex(vel);
			} else if ((midiStatus & 0xF0) == 0x80
			           || ((midiStatus & 0xF0) == 0x90 && vel == 0)) {
				if (midiData1 == midiNote) {
					noteOff();
					uart_puts_P("OFF ch=");
					uart_putc('0' + (midiStatus & 0x0F));
					uart_puts_P(" note=");
					printNote(midiData1);
				} else {
					uart_puts_P("---");
				}
			} else {
				uart_puts_P("???");
			}
			crlf();
			midiState = MIDI_WAIT_DATA1;
			break;
		}
		default:
			midiState = MIDI_WAIT_STATUS;
			break;
		}
	}
}
