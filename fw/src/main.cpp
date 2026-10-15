#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/sleep.h>
#include <util/delay.h>
#include "uart.h"
#include "midi.h"
#include "waveform.h"
#include "poly.h"
#include "envelope.h"

#ifdef POLY_VOICES
#define PWM_TOP POLY_PWM_TOP
#else
#define PWM_TOP 99
#endif

#define MIDI_BAUD 31250

static void initTimer2(void) {
	TCCR2A = (1 << COM2B1) | (1 << WGM21) | (1 << WGM20);
	TCCR2B = (1 << WGM22) | (1 << CS20);
	OCR2A = PWM_TOP;
	OCR2B = 0;
	DDRD |= (1 << 3);
}

static void initGPIO(void) {
	DDRD  |= (1 << 2) | (1 << 4) | (1 << 5) | (1 << 6) | (1 << 7);
	PORTD &= ~((1 << 2) | (1 << 4) | (1 << 5) | (1 << 6) | (1 << 7));

	DDRC  &= ~(1 << 1);
	PORTC |= (1 << 1);
}

#if defined(POT2_ADC) && !defined(SINE_ENV)
#error "POT2_ADC needs SINE_ENV: the second pot drives the envelope attack"
#endif

#ifndef POT2_ADC
static void initADC(void) {
	ADMUX  = (1 << REFS0) | (1 << ADLAR);
	ADCSRA = (1 << ADEN) | (1 << ADATE) | (1 << ADIE)
	       | (1 << ADPS2) | (1 << ADPS1) | (1 << ADPS0);
	ADCSRA |= (1 << ADSC);
}

ISR(ADC_vect) {
	potValue = ADCH;
}
#else
// Two pots: single conversions, alternating ADC0 and ADC<POT2_ADC>. The mux
// is switched between conversions, so each result belongs to its channel.
static void initADC(void) {
	ADMUX  = (1 << REFS0) | (1 << ADLAR);
	ADCSRA = (1 << ADEN) | (1 << ADIE) | (1 << ADSC)
	       | (1 << ADPS2) | (1 << ADPS1) | (1 << ADPS0);
}

ISR(ADC_vect) {
	static uint8_t ch;
	if (ch)
		pot2Value = ADCH;
	else
		potValue = ADCH;
	ch ^= 1;
	ADMUX = (1 << REFS0) | (1 << ADLAR) | (ch ? POT2_ADC : 0);
	ADCSRA |= (1 << ADSC);
}
#endif

static void initTimer1Btn(void) {
	TCCR1A = 0;
#ifdef SINE_ENV
	TCCR1B = (1 << WGM12) | (1 << CS11) | (1 << CS10);	// 1 ms: envelope tick
	OCR1A  = 249;
#else
	TCCR1B = (1 << WGM12) | (1 << CS12) | (1 << CS10);
	OCR1A  = 155;
#endif
	TIMSK1 = (1 << OCIE1A);
}

static uint8_t btnState = 0;
static uint8_t btnCounter = 0;

ISR(TIMER1_COMPA_vect) {
#ifdef SINE_ENV
	static uint8_t btnDiv = 0;
	msTicks++;
	if (++btnDiv < 10)	// button logic keeps its 10 ms tick
		return;
	btnDiv = 0;
#endif
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
				waveMode++;
				if (waveMode >= 3) waveMode = 0;
				PORTD &= ~((1 << 4) | (1 << 5) | (1 << 6));
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

	PORTD &= ~((1 << 4) | (1 << 5) | (1 << 6));
	PORTD |= (1 << (4 + waveMode));

	_delay_ms(1000);
	PORTD |= (1 << 2);

	sei();
	set_sleep_mode(SLEEP_MODE_IDLE);

	for (;;) {
#ifdef POLY_VOICES
		uart_poll();
		polyPoll();
#endif
#ifdef SINE_ENV
		envPoll();
#endif
		sleep_mode();
	}

	return 0;
}
