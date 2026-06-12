#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/sleep.h>
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
	ADCSRA = (1 << ADEN) | (1 << ADATE) | (1 << ADIE)
	       | (1 << ADPS2) | (1 << ADPS1) | (1 << ADPS0);
	ADCSRA |= (1 << ADSC);
}

ISR(ADC_vect) {
	potValue = ADCH;
}

static void initTimer1Btn(void) {
	TCCR1A = 0;
	TCCR1B = (1 << WGM12) | (1 << CS12) | (1 << CS10);
	OCR1A  = 155;
	TIMSK1 = (1 << OCIE1A);
}

static uint8_t btnState = 0;
static uint8_t btnCounter = 0;

ISR(TIMER1_COMPA_vect) {
	uint8_t btn = (PINC & (1 << 1)) ? 1 : 0;

	switch (btnState) {
	case 0:
		if (btn == 0) {
			btnState = 1;
			btnCounter = 3;
		}
		break;
	case 1:
		if (--btnCounter == 0) {
			if (btn == 0) {
				btnState = 2;
				noteOff();
				waveMode = (waveMode + 1) & 3;
				PORTD &= ~((1 << 4) | (1 << 5) | (1 << 6) | (1 << 7));
				PORTD |= (1 << (4 + waveMode));
			} else {
				btnState = 0;
			}
		}
		break;
	case 2:
		if (btn == 1)
			btnState = 0;
		break;
	}
}

int main(void) {
	initTimer2();
	initGPIO();
	initADC();
	initTimer1Btn();
	initWaveform();
	uart_init(UART_BAUD_SELECT(MIDI_BAUD, F_CPU));

	PORTD &= ~((1 << 4) | (1 << 5) | (1 << 6) | (1 << 7));
	PORTD |= (1 << (4 + waveMode));

	_delay_ms(1000);
	PORTD |= (1 << 2);

	sei();
	set_sleep_mode(SLEEP_MODE_IDLE);

	for (;;)
		sleep_mode();

	return 0;
}
