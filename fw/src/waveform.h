#ifndef WAVEFORM_H
#define WAVEFORM_H

#include <avr/io.h>

extern volatile uint8_t potValue;
extern volatile uint8_t waveMode;

void initWaveform(void);

#endif
