#ifdef POLY_VOICES

#include "poly.h"
#include "midi.h"
#include "waveform.h"
#include "envelope.h"
#include <avr/interrupt.h>
#include <util/atomic.h>
#include <math.h>

#if POLY_ACC_BITS == 24
typedef __uint24 acc_t;
#else
typedef uint16_t acc_t;
#endif

#if POLY_VOICES < 1 || POLY_VOICES > 16
#error "POLY_VOICES must be 1..16 (VOICE() is unrolled 16 times)"
#endif

// Sample ISR cost measured from the listing (tools/isrcycles.py), worst case
// with all voices active: ~77 + 30*N cycles (24-bit acc), ~65 + 22*N (16-bit).
// With SINE_ENV the sine path (envelope multiply) is the longest one.
#if defined(SINE_ENV) && POLY_ACC_BITS == 24
#define POLY_ISR_CYCLES (86 + 36 * POLY_VOICES)
#elif defined(SINE_ENV)
#define POLY_ISR_CYCLES (74 + 28 * POLY_VOICES)
#elif POLY_ACC_BITS == 24
#define POLY_ISR_CYCLES (77 + 30 * POLY_VOICES)
#else
#define POLY_ISR_CYCLES (65 + 22 * POLY_VOICES)
#endif
#define POLY_SAMPLE_CYCLES (F_CPU / POLY_FS)

#if POLY_ISR_CYCLES * 100 > POLY_SAMPLE_CYCLES * 90
#error "POLY_VOICES too high for POLY_FS: sample ISR would take > 90% CPU"
#elif POLY_ISR_CYCLES * 100 > POLY_SAMPLE_CYCLES * 70
#warning "Sample ISR takes > 70% CPU: little time left for MIDI and the main loop"
#endif

#if POLY_PWM_TOP / POLY_VOICES < 16
#warning "Fewer than 16 PWM levels per voice: expect audible quantization"
#endif

#define N   POLY_VOICES
#define AMP (POLY_PWM_TOP / N)	// per-voice amplitude, sum never exceeds TOP

// phase increments for notes 120..131 at 2^32 scale, shifted down per octave
#define INC(f) ((uint32_t)((f) * 4294967296.0 / POLY_FS + 0.5))
static const uint32_t incTop[12] = {
	INC(8372.018), INC(8869.844), INC(9397.273), INC(9956.063),
	INC(10548.08), INC(11175.30), INC(11839.82), INC(12543.85),
	INC(13289.75), INC(14080.00), INC(14917.24), INC(15804.27)
};

static acc_t acc[N];
static acc_t inc[N];
static uint8_t vnote[N];
static uint16_t vstamp[N];
static uint16_t stamp;
static uint8_t outNext;
// 256-byte aligned: the sample index becomes the low address byte directly
static uint8_t wavetable[256] __attribute__((aligned(256)));
static uint8_t sineTable[256];	// computed once: sinf() x256 takes ~30 ms

static uint8_t tblMode = 0xFF;
static uint8_t tblPot = 0xFF;

#ifdef SINE_ENV
// Sine mode with envelope: the table holds signed samples (-HALF..HALF),
// each voice is scaled by its envelope and the sum is centred on BIAS, so
// silent voices sit at mid-scale and fades end without a DC step.
#define HALF (AMP / 2)
#define BIAS (POLY_PWM_TOP / 2)
static Env venv[N];
static uint8_t venvOut[N];
static uint8_t envMode;		// 1 while the sine table is active
#endif

// Runs in main loop with interrupts enabled; no divisions inside loops so a
// pot sweep does not stall MIDI parsing (rx buffer holds ~5 ms of bytes).
static void buildTable(uint8_t mode, uint8_t pot) {
	switch (mode) {
	case 0: {	// square, pot = duty
		for (uint16_t i = 0; i < 256; i++)
			wavetable[i] = (i < pot) ? AMP : 0;
		break;
	}
	case 1: {	// triangle, pot = rise/fall split (pot <= 252)
		uint8_t split = pot;
		uint16_t v = 0;
		uint16_t up = split ? ((uint16_t)AMP << 8) / split : 0;
		uint16_t dn = ((uint16_t)AMP << 8) / (255 - split);
		uint16_t i;
		for (i = 0; i < split; i++) {
			wavetable[i] = v >> 8;
			v += up;
		}
		v = (uint16_t)AMP << 8;
		for (; i < 256; i++) {
			wavetable[i] = v >> 8;
			v -= dn;
		}
		break;
	}
	case 2: {	// sine
		for (uint16_t i = 0; i < 256; i++)
			wavetable[i] = sineTable[i];
		break;
	}
	}
}

void initWaveform(void) {
	TCCR0A = (1 << WGM01);
	OCR0A  = F_CPU / 8 / POLY_FS - 1;
	TCCR0B = (1 << CS01);
	TIMSK0 |= (1 << OCIE0A);

	for (uint16_t i = 0; i < 256; i++)
#ifdef SINE_ENV
		sineTable[i] = (uint8_t)(int8_t)lroundf(sinf((float)i * (float)M_PI / 128.0f) * HALF);
#else
		sineTable[i] = (uint8_t)((sinf((float)i * (float)M_PI / 128.0f) + 1.0f)
		                         * (AMP / 2.0f) + 0.5f);
#endif
	for (uint8_t v = 0; v < N; v++)
		vnote[v] = 0xFF;
	polyPoll();
}

// Rebuild the wavetable when mode or pot changes; called from the main loop.
void polyPoll(void) {
	uint8_t mode = waveMode;
	uint8_t pot = potValue & 0xFC;
	if (mode == 2)
		pot = 0;
	if (mode == tblMode && pot == tblPot)
		return;
	tblMode = mode;
	tblPot = pot;
#ifdef SINE_ENV
	envMode = 0;
	buildTable(mode, pot);
	envMode = (mode == 2);
#else
	buildTable(mode, pot);
#endif
}

// wavetable[idx] as ZL = idx, ZH = hi8(wavetable): 4 cycles
static inline uint8_t lookup(uint8_t idx) {
	uint8_t v;
	asm ("mov r30, %1\n\t"
	     "ldi r31, hi8(%2)\n\t"
	     "ld %0, Z"
	     : "=r" (v) : "r" (idx), "i" (wavetable) : "r30", "r31");
	return v;
}

#define VOICE(i) \
	if (N > i && inc[i]) { \
		acc_t a = acc[i] + inc[i]; \
		acc[i] = a; \
		sum += lookup((uint8_t)(a >> (POLY_ACC_BITS - 8))); \
	}

#ifdef SINE_ENV
#define VOICE_ENV(i) \
	if (N > i && inc[i]) { \
		acc_t a = acc[i] + inc[i]; \
		acc[i] = a; \
		int8_t s = (int8_t)lookup((uint8_t)(a >> (POLY_ACC_BITS - 8))); \
		ssum += (int8_t)(((int16_t)s * venvOut[i]) >> 8); \
	}
#endif

ISR(TIMER0_COMPA_vect) {
	OCR2B = outNext;	// output first: no jitter from voice count

#ifdef SINE_ENV
	if (envMode) {
		asm volatile ("" ::: "memory");	// keep voice loads inside each path
		int8_t ssum = 0;
		VOICE_ENV(0)  VOICE_ENV(1)  VOICE_ENV(2)  VOICE_ENV(3)
		VOICE_ENV(4)  VOICE_ENV(5)  VOICE_ENV(6)  VOICE_ENV(7)
		VOICE_ENV(8)  VOICE_ENV(9)  VOICE_ENV(10) VOICE_ENV(11)
		VOICE_ENV(12) VOICE_ENV(13) VOICE_ENV(14) VOICE_ENV(15)
		outNext = BIAS + ssum;
		return;
	}
	asm volatile ("" ::: "memory");
#endif

	uint8_t sum = 0;
	VOICE(0)  VOICE(1)  VOICE(2)  VOICE(3)
	VOICE(4)  VOICE(5)  VOICE(6)  VOICE(7)
	VOICE(8)  VOICE(9)  VOICE(10) VOICE(11)
	VOICE(12) VOICE(13) VOICE(14) VOICE(15)
	outNext = sum;
}

static void updateLed(void) {
	for (uint8_t v = 0; v < N; v++) {
#ifdef SINE_ENV
		if (inc[v]) {		// releasing voices still sound
#else
		if (vnote[v] != 0xFF) {
#endif
			PORTD |= (1 << 7);
			midiActive = 1;
			return;
		}
	}
	PORTD &= ~(1 << 7);
	midiActive = 0;
}

// Runs in main loop (uart_poll). Voice state is shared with the sample ISR and
// the button ISR (noteOff), so allocation + commit is atomic (~150 cycles).
void noteOn(uint8_t note) {
	uint32_t i32 = incTop[note % 12] >> (10 - note / 12);
	if (i32 >= 0x80000000UL)	// above Nyquist
		return;

	acc_t newInc = (acc_t)(i32 >> (32 - POLY_ACC_BITS));

	ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
		uint8_t v, pick = 0;
		uint16_t oldest = 0;
		for (v = 0; v < N; v++)
			if (vnote[v] == note)
				break;
#ifdef SINE_ENV
		uint8_t retrigger = (v < N);
		if (v == N) {
			for (v = 0; v < N; v++)
				if (inc[v] == 0)	// not even releasing
					break;
		}
#else
		if (v == N) {
			for (v = 0; v < N; v++)
				if (vnote[v] == 0xFF)
					break;
		}
#endif
		if (v == N) {	// steal the oldest voice
			for (uint8_t k = 0; k < N; k++) {
				uint16_t age = stamp - vstamp[k];
				if (age >= oldest) {
					oldest = age;
					pick = k;
				}
			}
			v = pick;
		}

		vnote[v] = note;
		vstamp[v] = ++stamp;
#ifdef SINE_ENV
		if (!retrigger) {	// same held note keeps phase and level
			acc[v] = 0;
			venv[v].level = 0;
		}
		envStart(&venv[v]);
		venvOut[v] = venv[v].level >> 8;
#else
		acc[v] = 0;
#endif
		inc[v] = newInc;
		updateLed();
	}
}

void noteRelease(uint8_t note) {
	ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
		for (uint8_t v = 0; v < N; v++) {
			if (vnote[v] == note) {
				vnote[v] = 0xFF;
#ifdef SINE_ENV
				if (envMode) {
					envRelease(&venv[v]);
					continue;
				}
#endif
				inc[v] = 0;
			}
		}
		updateLed();
	}
}

void noteOff(void) {
	ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
		for (uint8_t v = 0; v < N; v++) {
			vnote[v] = 0xFF;
			inc[v] = 0;
		}
#ifdef SINE_ENV
		outNext = envMode ? BIAS : 0;
#else
		outNext = 0;
#endif
		OCR2B = outNext;
		updateLed();
	}
}

#ifdef SINE_ENV
// Main loop: 1 ms envelope steps for every sounding voice.
void envPoll(void) {
	uint8_t n = envElapsed();
	if (!envMode)
		return;
	envSetPot(potValue);
	uint8_t ended = 0;
	while (n--) {
		for (uint8_t v = 0; v < N; v++) {
			ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
				if (inc[v]) {
					venvOut[v] = envStep(&venv[v]);
					if (venv[v].stage == ENV_IDLE) {
						inc[v] = 0;
						vnote[v] = 0xFF;
						ended = 1;
					}
				}
			}
		}
	}
	if (ended) {
		ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
			updateLed();
		}
	}
}
#endif

#endif
