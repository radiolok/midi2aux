#ifdef POLY_VOICES

#include "poly.h"
#include "midi.h"
#include "waveform.h"
#include "envelope.h"
#include <avr/interrupt.h>
#include <util/atomic.h>
#include <math.h>

#if POLY_ACC_BITS == 24 && defined(__AVR__)
typedef __uint24 acc_t;
#define ACC_WRAP(x) (x)
#elif POLY_ACC_BITS == 24
typedef uint32_t acc_t;				// host simulation (tools/sim)
#define ACC_WRAP(x) ((x) & 0xFFFFFFUL)
#else
typedef uint16_t acc_t;
#define ACC_WRAP(x) ((acc_t)(x))
#endif

#if POLY_VOICES < 1 || POLY_VOICES > 16
#error "POLY_VOICES must be 1..16 (VOICE() is unrolled 16 times)"
#endif

// Sample ISR cost measured from the listing (tools/isrcycles.py), worst case
// with all voices active: ~77 + 30*N cycles (24-bit acc), ~65 + 22*N (16-bit).
// With SINE_ENV every voice is multiplied by its gain and the sum is clamped:
// estimated ~95 + 40*N (24-bit); re-check with tools/isrcycles.py.
#if defined(SINE_ENV) && POLY_ACC_BITS == 24
#define POLY_ISR_CYCLES (95 + 40 * POLY_VOICES)
#elif defined(SINE_ENV)
#define POLY_ISR_CYCLES (83 + 32 * POLY_VOICES)
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

#if POLY_PWM_TOP / POLY_VOICES < 16 && !defined(SINE_ENV)
#warning "Fewer than 16 PWM levels per voice: expect audible quantization"
#endif

#define N   POLY_VOICES
#define AMP (POLY_PWM_TOP / N)	// no SINE_ENV: per-voice amplitude, sum never exceeds TOP

#ifndef POLY_DRIVE
#define POLY_DRIVE 100	// SINE_ENV gain normalisation, % (100: the sum can never clip)
#endif

// Timer2 start value that puts its BOTTOM (where OCR2B is latched) right at the
// sample interrupt, so the ISR's OCR2B write always lands early in a PWM cycle
// and every sample lasts exactly two PWM periods. See initWaveform().
#ifndef POLY_T2_PHASE
#define POLY_T2_PHASE 8
#endif

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
// Envelope build: every waveform is a signed full-scale table (-HALF..HALF).
// Each voice is scaled by vgain = envelope x master gain and the sum is
// centred on BIAS, so silent voices sit at mid-scale and fades end without a
// DC step. The master gain keeps sum(vgain) <= 255 * POLY_DRIVE / 100: a
// single note plays at full scale, a chord is turned down so it cannot clip.
#define HALF (POLY_PWM_TOP / 2)
#define BIAS (POLY_PWM_TOP / 2)
static Env venv[N];
static uint8_t venvOut[N];	// envelope level, main loop only
static uint8_t vgain[N];	// read by the sample ISR
static uint8_t master = 255;
#endif

// Runs in main loop with interrupts enabled; no divisions inside loops so a
// pot sweep does not stall MIDI parsing (rx buffer holds ~5 ms of bytes).
#ifdef SINE_ENV
// Signed tables, -HALF..HALF; stored as uint8_t, read back as int8_t.
#define LO   ((uint8_t)(-HALF))
#define HI   ((uint8_t)HALF)
#define SPAN (2 * HALF)
#define OFS  HALF
#else
#define LO   0
#define HI   AMP
#define SPAN AMP
#define OFS  0
#endif

static void buildTable(uint8_t mode, uint8_t pot) {
	switch (mode) {
	case 0: {	// square, pot = duty
		for (uint16_t i = 0; i < 256; i++)
			wavetable[i] = (i < pot) ? HI : LO;
		break;
	}
	case 1: {	// triangle, pot = rise/fall split (pot <= 252)
		uint8_t split = pot;
		uint16_t v = 0;
		uint16_t up = split ? ((uint16_t)SPAN << 8) / split : 0;
		uint16_t dn = ((uint16_t)SPAN << 8) / (255 - split);
		uint16_t i;
		for (i = 0; i < split; i++) {
			wavetable[i] = (uint8_t)((v >> 8) - OFS);
			v += up;
		}
		v = (uint16_t)SPAN << 8;
		for (; i < 256; i++) {
			wavetable[i] = (uint8_t)((v >> 8) - OFS);
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
	for (uint16_t i = 0; i < 256; i++)
#ifdef SINE_ENV
		sineTable[i] = (uint8_t)(int8_t)lroundf(sinf((float)i * (float)M_PI / 128.0f) * HALF);
#else
		sineTable[i] = (uint8_t)((sinf((float)i * (float)M_PI / 128.0f) + 1.0f)
		                         * (AMP / 2.0f) + 0.5f);
#endif
	for (uint8_t v = 0; v < N; v++)
		vnote[v] = 0xFF;
#ifdef SINE_ENV
	outNext = BIAS;
	OCR2B = BIAS;
#endif
	polyPoll();

	// Sample clock: Timer0 CTC, 512 cycles = two Timer2 PWM periods. Both
	// timers are started from a known phase (interrupts are still off here):
	// Timer0's prescaler is reset, Timer2 is restarted at POLY_T2_PHASE, so
	// Timer2 reaches BOTTOM ~8 cycles after the compare match. OCR2B is
	// latched at BOTTOM; the ISR writes it ~40 cycles later, which leaves
	// ~200 cycles for other interrupts or atomic blocks to delay the ISR
	// before a sample would slip into the neighbouring PWM period.
	uint8_t t2b = TCCR2B;
	TCCR2B = t2b & ~((1 << CS22) | (1 << CS21) | (1 << CS20));
	TCCR0A = (1 << WGM01);
	OCR0A  = F_CPU / 8 / POLY_FS - 1;
	TCCR0B = (1 << CS01);
	GTCCR  = (1 << PSRSYNC);
	TCNT0  = 0;
	TCNT2  = POLY_T2_PHASE;
	TCCR2B = t2b;
	TIFR0  = (1 << OCF0A);
	TIMSK0 |= (1 << OCIE0A);
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
	buildTable(mode, pot);
}

// wavetable[idx] as ZL = idx, ZH = hi8(wavetable): 4 cycles
static inline uint8_t lookup(uint8_t idx) {
#ifdef __AVR__
	uint8_t v;
	asm ("mov r30, %1\n\t"
	     "ldi r31, hi8(%2)\n\t"
	     "ld %0, Z"
	     : "=r" (v) : "r" (idx), "i" (wavetable) : "r30", "r31");
	return v;
#else
	return wavetable[idx];
#endif
}

#define VOICE(i) \
	if (N > i && inc[i]) { \
		acc_t a = ACC_WRAP(acc[i] + inc[i]); \
		acc[i] = a; \
		sum += lookup((uint8_t)(a >> (POLY_ACC_BITS - 8))); \
	}

#ifdef SINE_ENV
#define VOICE_ENV(i) \
	if (N > i && inc[i]) { \
		acc_t a = ACC_WRAP(acc[i] + inc[i]); \
		acc[i] = a; \
		int8_t s = (int8_t)lookup((uint8_t)(a >> (POLY_ACC_BITS - 8))); \
		sum += (int8_t)(((int16_t)s * vgain[i]) >> 8); \
	}
#endif

ISR(TIMER0_COMPA_vect) {
	OCR2B = outNext;	// output first: no jitter from voice count

#ifdef SINE_ENV
	int16_t sum = 0;
	VOICE_ENV(0)  VOICE_ENV(1)  VOICE_ENV(2)  VOICE_ENV(3)
	VOICE_ENV(4)  VOICE_ENV(5)  VOICE_ENV(6)  VOICE_ENV(7)
	VOICE_ENV(8)  VOICE_ENV(9)  VOICE_ENV(10) VOICE_ENV(11)
	VOICE_ENV(12) VOICE_ENV(13) VOICE_ENV(14) VOICE_ENV(15)
	if (sum > HALF)
		sum = HALF;
	else if (sum < -HALF)
		sum = -HALF;
	outNext = (uint8_t)(BIAS + sum);
#else
	uint8_t sum = 0;
	VOICE(0)  VOICE(1)  VOICE(2)  VOICE(3)
	VOICE(4)  VOICE(5)  VOICE(6)  VOICE(7)
	VOICE(8)  VOICE(9)  VOICE(10) VOICE(11)
	VOICE(12) VOICE(13) VOICE(14) VOICE(15)
	outNext = sum;
#endif
}

static void updateLed(void) {
	for (uint8_t v = 0; v < N; v++) {
		if (inc[v]) {		// releasing voices still sound
			PORTD |= (1 << 7);
			midiActive = 1;
			return;
		}
	}
	PORTD &= ~(1 << 7);
	midiActive = 0;
}

// Voice bookkeeping (vnote, vstamp, venv) belongs to the main loop: noteOn,
// noteRelease and envPoll all run there. Only the button ISR (noteOff) also
// touches it, and it only silences. So the voice search runs with interrupts
// on, and only the multi-byte writes the sample ISR reads are atomic: the
// sample interrupt is never held off for long (see initWaveform).
void noteOn(uint8_t note) {
	uint32_t i32 = incTop[note % 12] >> (10 - note / 12);
	if (i32 >= 0x80000000UL)	// above Nyquist
		return;

	acc_t newInc = (acc_t)(i32 >> (32 - POLY_ACC_BITS));
	uint8_t v;
	uint8_t fresh = 0;	// 1: voice was silent, start from phase 0 and level 0

	for (v = 0; v < N; v++)		// same note: retrigger
		if (vnote[v] == note)
			break;
	if (v == N) {			// a free voice
		for (v = 0; v < N; v++)
			if (inc[v] == 0)
				break;
		fresh = (v < N);
	}
	if (v == N) {			// steal the oldest voice ...
		uint8_t pick = 0, rel = 0;
		uint16_t oldest = 0;
		for (uint8_t k = 0; k < N; k++) {
#ifdef SINE_ENV
			uint8_t r = (vnote[k] == 0xFF);	// ... preferring released ones
			if (r < rel)
				continue;
			if (r > rel) {
				rel = r;
				oldest = 0;
			}
#endif
			uint16_t age = stamp - vstamp[k];
			if (age >= oldest) {
				oldest = age;
				pick = k;
			}
		}
		(void)rel;
		v = pick;
	}

	vnote[v] = note;
	vstamp[v] = ++stamp;
#ifdef SINE_ENV
	// A stolen voice keeps its phase and envelope level: the pitch changes
	// on the fly and the new attack starts from where the old note was, as
	// in the mono firmware. Zeroing them is what clicked on every note.
	if (fresh) {
		venv[v].level = 0;
		venvOut[v] = 0;
		vgain[v] = 0;
	}
	envStart(&venv[v]);
	ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
		if (fresh)
			acc[v] = 0;
		inc[v] = newInc;
	}
#else
	(void)fresh;
	ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
		acc[v] = 0;
		inc[v] = newInc;
	}
#endif
	updateLed();
}

void noteRelease(uint8_t note) {
	for (uint8_t v = 0; v < N; v++) {
		if (vnote[v] == note) {
			vnote[v] = 0xFF;
#ifdef SINE_ENV
			envRelease(&venv[v]);	// the voice stops when the envelope ends
#else
			ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
				inc[v] = 0;
			}
#endif
		}
	}
	updateLed();
}

void noteOff(void) {
	ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
		for (uint8_t v = 0; v < N; v++) {
			vnote[v] = 0xFF;
			inc[v] = 0;
		}
#ifdef SINE_ENV
		outNext = BIAS;
#else
		outNext = 0;
#endif
		OCR2B = outNext;
		updateLed();
	}
}

#ifdef SINE_ENV
// Main loop: 1 ms envelope steps for every sounding voice, then the master
// gain and the per-voice gains the sample ISR uses.
void envPoll(void) {
	uint8_t n = envElapsed();
	if (!n)
		return;
	envConfig(waveMode == 2 ? ENV_MORPH : ENV_GATE, potValue, pot2Value);

	uint8_t ended = 0;
	while (n--) {
		for (uint8_t v = 0; v < N; v++) {
			if (!inc[v]) {
				venvOut[v] = 0;
				continue;
			}
			venvOut[v] = envStep(&venv[v]);
			if (venv[v].stage == ENV_IDLE) {
				ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
					inc[v] = 0;
				}
				vnote[v] = 0xFF;
				venvOut[v] = 0;
				ended = 1;
			}
		}
		// Normalisation: the gain falls at once when voices are added (the
		// sum must not clip) and recovers at ~1 step/ms when they fade.
		uint16_t total = 0;
		for (uint8_t v = 0; v < N; v++)
			total += venvOut[v];
		uint8_t target = 255;
		if (total > 255) {
			uint32_t t = (uint32_t)65025UL * POLY_DRIVE / 100 / total;
			if (t < 255)
				target = (uint8_t)t;
		}
		if (target < master)
			master = target;
		else if (master < target)
			master++;
	}

	for (uint8_t v = 0; v < N; v++)
		vgain[v] = ((uint16_t)venvOut[v] * master) >> 8;

	if (ended)
		updateLed();
}
#endif

#endif
