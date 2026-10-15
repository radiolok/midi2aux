#ifndef WAVEFORM_H
#define WAVEFORM_H

#include <avr/io.h>

extern volatile uint8_t potValue;
extern volatile uint8_t pot2Value;	// second pot (POT2_ADC), else unused
extern volatile uint8_t waveMode;
extern volatile uint8_t envOut;	// mono sine envelope level (SINE_ENV)

void initWaveform(void);

#endif
