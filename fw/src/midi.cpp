#include "midi.h"
#include <avr/pgmspace.h>
#include <util/delay.h>
#include "uart.h"

#define DBG_PORT PORTB
#define DBG_DDR  DDRB
#define DBG_PIN  0

static void dbg_putc(uint8_t c) {
	DBG_PORT &= ~(1 << DBG_PIN);
	_delay_us(26);
	for (uint8_t i = 0; i < 8; i++) {
		if (c & 1)
			DBG_PORT |= (1 << DBG_PIN);
		else
			DBG_PORT &= ~(1 << DBG_PIN);
		_delay_us(26);
		c >>= 1;
	}
	DBG_PORT |= (1 << DBG_PIN);
	_delay_us(26);
}

static void dbg_puts(const char *s) {
	while (*s) dbg_putc(*s++);
}

static void dbg_puts_P(const char *s) {
	char c;
	while ((c = pgm_read_byte(s++))) dbg_putc(c);
}

static void dbg_puthex(uint8_t val) {
	uint8_t hi = (val >> 4) & 0x0F;
	uint8_t lo = val & 0x0F;
	dbg_putc(hi < 10 ? '0' + hi : 'A' + hi - 10);
	dbg_putc(lo < 10 ? '0' + lo : 'A' + lo - 10);
}

static void dbg_crlf(void) {
	dbg_putc('\r');
	dbg_putc('\n');
}

void dbg_init(void) {
	DBG_DDR |= (1 << DBG_PIN);
	DBG_PORT |= (1 << DBG_PIN);
}

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

static void printNote(uint8_t note) {
	uint8_t semi = note % 12;
	uint8_t oct  = note / 12;
	dbg_putc(pgm_read_byte(&notename_letter[semi]));
	char sign = pgm_read_byte(&notename_sign[semi]);
	if (sign != ' ') dbg_putc(sign);
	if (oct < 10) {
		dbg_putc('0' + oct);
	} else {
		dbg_putc('0' + oct / 10);
		dbg_putc('0' + oct % 10);
	}
}

void midiParser(uint8_t byte) {
	dbg_puthex(byte);
	dbg_putc(' ');

	if (byte & 0x80) {
		if (byte == 0xFC) {
			dbg_crlf();
			noteOff();
			return;
		}
		if (byte >= 0xF8) {
			dbg_crlf();
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
				dbg_puts_P(PSTR("ON  ch="));
				dbg_putc('0' + (midiStatus & 0x0F));
				dbg_puts_P(PSTR(" note="));
				printNote(midiNote);
				dbg_puts_P(PSTR(" vel="));
				dbg_puthex(vel);
			} else if ((midiStatus & 0xF0) == 0x80
			           || ((midiStatus & 0xF0) == 0x90 && vel == 0)) {
				if (midiData1 == midiNote) {
					noteOff();
					dbg_puts_P(PSTR("OFF ch="));
					dbg_putc('0' + (midiStatus & 0x0F));
					dbg_puts_P(PSTR(" note="));
					printNote(midiData1);
				} else {
					dbg_puts_P(PSTR("---"));
				}
			} else {
				dbg_puts_P(PSTR("???"));
			}
			dbg_crlf();
			midiState = MIDI_WAIT_DATA1;
			break;
		}
		default:
			midiState = MIDI_WAIT_STATUS;
			break;
		}
	}
}
