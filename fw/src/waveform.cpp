#include "waveform.h"
#include <avr/interrupt.h>
#include <math.h>

volatile uint8_t potValue = 0;
volatile uint8_t waveMode = 0;
static volatile uint8_t phase = 0;
static uint8_t sine[16];

void initWaveform(void) {
	TCCR0A = (1 << WGM01);
	TCCR0B = 0;

	for (uint8_t i = 0; i < 16; i++) {
		sine[i] = (uint8_t)(sinf((float)i * (float)M_PI / 32.0f) * 49.0f + 0.5f);
	}

	phase = 0;
}

ISR(TIMER0_COMPA_vect) {
	uint8_t pot = potValue;
	uint8_t mode = waveMode;
	uint8_t pwm = 0;

	switch (mode) {
	case 0: {
		uint8_t threshold = ((uint16_t)pot + 2) >> 2;
		if (phase < threshold)
			pwm = 99;
		else
			pwm = 0;
		break;
	}
	case 1: {
		uint8_t split = pot >> 2;
		if (split == 0) {
			pwm = (uint8_t)(((uint16_t)(63 - phase) * 99) / 63);
		} else if (phase <= split) {
			pwm = (uint8_t)(((uint16_t)phase * 99) / split);
		} else {
			uint8_t d = 63 - split;
			if (d > 0)
				pwm = (uint8_t)(((uint16_t)(63 - phase) * 99) / d);
			else
				pwm = 99;
		}
		break;
	}
	case 2: {
		if (phase < 16)
			pwm = 50 + sine[phase];
		else if (phase < 32)
			pwm = 50 + sine[31 - phase];
		else if (phase < 48)
			pwm = 50 - sine[phase - 32];
		else
			pwm = 50 - sine[63 - phase];
		break;
	}
	}

	OCR2B = pwm;

	phase++;
	if (phase >= 64)
		phase = 0;
}
