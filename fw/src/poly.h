#ifndef POLY_H
#define POLY_H

#include <avr/io.h>

#ifdef POLY_VOICES

#ifndef POLY_FS
#define POLY_FS 31250		// sample rate, Hz (Timer0 CTC, prescaler 8)
#endif

#ifndef POLY_PWM_TOP
#define POLY_PWM_TOP 255	// Timer2 TOP: 255 -> 62.5 kHz / 256 steps, 99 -> 160 kHz / 100 steps
#endif

#ifndef POLY_ACC_BITS
#define POLY_ACC_BITS 24	// phase accumulator width: 16 or 24
#endif

void noteRelease(uint8_t note);
void polyPoll(void);

#endif

#endif
