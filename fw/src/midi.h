#ifndef MIDI_H
#define MIDI_H

#include <avr/io.h>

void midiParser(uint8_t byte);
uint16_t getNotePeriod(uint8_t note);
void noteOn(uint8_t note);
void noteOff(void);

void dbg_init(void);

extern volatile uint8_t midiActive;

#endif
