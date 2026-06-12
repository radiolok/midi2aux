#include <avr/io.h>
#include <avr/interrupt.h>
#include <util/delay.h>
#include "uart.h"
#include "midi.h"
#include "waveform.h"

#define MIDI_BAUD 31250

static void initTimer2(void) {
	TCCR2A = (1 << COM2B1) | (1 << WGM21) | (1 << WGM20);
	TCCR2B = (1 << WGM22) | (1 << CS20);
	OCR2A = 99;
	OCR2B = 0;

	DDRD |= (1 << 3);
}

static void initGPIO(void) {
	DDRD  |= (1 << 2) | (1 << 4) | (1 << 5) | (1 << 6) | (1 << 7);
	PORTD &= ~((1 << 2) | (1 << 4) | (1 << 5) | (1 << 6) | (1 << 7));

	DDRC  &= ~(1 << 1);
	PORTC |= (1 << 1);
}

static void initADC(void) {
	ADMUX  = (1 << REFS0) | (1 << ADLAR);
	ADCSRA = (1 << ADEN) | (1 << ADPS2) | (1 << ADPS1) | (1 << ADPS0);
}

static void updateLEDs(void) {
	PORTD &= ~((1 << 4) | (1 << 5) | (1 << 6) | (1 << 7));
	PORTD |= (1 << (4 + waveMode));
}

int main(void) {
	initTimer2();
	initGPIO();
	initADC();
	initWaveform();
	uart_init(UART_BAUD_SELECT(MIDI_BAUD, F_CPU));

	updateLEDs();
	_delay_ms(1000);
	PORTD |= (1 << 2);
	sei();

	uint8_t btnPrev = 1;
	uint8_t btnStable = 1;

	for (;;) {
		ADCSRA |= (1 << ADSC);
		while (ADCSRA & (1 << ADSC));
		potValue = ADCH;

		uint8_t btnRaw = (PINC & (1 << 1)) ? 1 : 0;

		if (btnRaw != btnPrev) {
			_delay_ms(30);
			btnRaw = (PINC & (1 << 1)) ? 1 : 0;
			if (btnRaw == btnPrev) {
				btnStable = btnRaw;
			} else {
				btnStable = btnRaw;
				if (btnStable == 0) {
					waveMode = (waveMode + 1) & 3;
					updateLEDs();
				}
			}
		}

		btnPrev = btnRaw;

		while (uart_available()) {
			midiParser(uart_getc());
		}
	}

	return 0;
}
