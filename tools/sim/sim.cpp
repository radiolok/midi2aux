// Host simulation of the poly + envelope engine (no avr-gcc needed).
// Builds poly.cpp / envelope.cpp / midi.cpp for x86 with mocked registers,
// drives MIDI bytes, runs the sample ISR at 31.25 kHz and the 1 ms envelope
// tick, and writes the PWM duty sequence as a 16-bit WAV.
//   usage: sim <scenario> <out.wav> [pot] [mode]
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <vector>
#include <avr/io.h>
#include "../../fw/src/midi.h"
#include "../../fw/src/waveform.h"
#include "../../fw/src/envelope.h"
#include "../../fw/src/poly.h"

extern "C" void TIMER0_COMPA_vect(void);

static std::vector<int16_t> out;
static long t;	// samples

static void midi(uint8_t a, uint8_t b, uint8_t c) { midiParser(a); midiParser(b); midiParser(c); }
static void on(uint8_t n)  { midi(0x90, n, 100); }
static void off(uint8_t n) { midi(0x80, n, 0); }

static void run(double ms) {
	long end = t + (long)(ms * POLY_FS / 1000.0);
	for (; t < end; t++) {
		TIMER0_COMPA_vect();
		if ((t * 1000L) / POLY_FS != ((t + 1) * 1000L) / POLY_FS)
			msTicks++;
		polyPoll();
		envPoll();
		out.push_back((int16_t)(((int)OCR2B - POLY_PWM_TOP / 2) * 256));
	}
}

static void wav(const char *fn) {
	FILE *f = fopen(fn, "wb");
	uint32_t n = out.size() * 2, sr = POLY_FS, br = sr * 2;
	fwrite("RIFF", 1, 4, f); uint32_t x = 36 + n; fwrite(&x, 4, 1, f);
	fwrite("WAVEfmt ", 1, 8, f); x = 16; fwrite(&x, 4, 1, f);
	uint16_t h[] = {1, 1}; fwrite(h, 2, 2, f); fwrite(&sr, 4, 1, f); fwrite(&br, 4, 1, f);
	uint16_t h2[] = {2, 16}; fwrite(h2, 2, 2, f);
	fwrite("data", 1, 4, f); fwrite(&n, 4, 1, f);
	fwrite(out.data(), 2, out.size(), f); fclose(f);
}

int main(int argc, char **argv) {
	const char *sc = argv[1];
	potValue = argc > 3 ? atoi(argv[3]) : 200;
	waveMode = argc > 4 ? atoi(argv[4]) : 2;
	initWaveform();
	run(20);
	if (!strcmp(sc, "legato")) {		// melody, each note overlaps the next
		uint8_t m[] = {60, 64, 67, 72, 67, 64, 60, 55};
		for (int i = 0; i < 8; i++) {
			on(m[i]); run(150);
			if (i) off(m[i - 1]);
			run(100);
		}
		off(m[7]); run(1500);
	} else if (!strcmp(sc, "staccato")) {	// separate notes, tails overlap the next
		uint8_t m[] = {60, 64, 67, 72, 67, 64, 60, 55};
		for (int i = 0; i < 8; i++) { on(m[i]); run(150); off(m[i]); run(100); }
		run(1500);
	} else if (!strcmp(sc, "chord")) {	// one note, then a 4-note chord, then one
		on(60); run(800); off(60); run(400);
		on(60); on(64); on(67); on(72); run(1200);
		off(60); off(64); off(67); off(72); run(1200);
		on(67); run(800); off(67); run(1500);
	}
	wav(argv[2]);
	int mx = -999, mn = 999;
	for (int16_t s : out) { if (s / 256 > mx) mx = s / 256; if (s / 256 < mn) mn = s / 256; }
	fprintf(stderr, "%s: %zu samples, duty-BIAS min %d max %d\n", argv[2], out.size(), mn, mx);
	return 0;
}
