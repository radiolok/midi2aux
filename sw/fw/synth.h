/* Synth control: MIDI events -> voice allocation -> engine registers.
 * Register access goes through hw_write / hw_read so the logic is host-testable. */
#ifndef SYNTH_H
#define SYNTH_H

#include <stdint.h>

#include "params.h"
#include "voice_alloc.h"

enum { WAVE_SAW, WAVE_SQUARE, WAVE_TRI, WAVE_SINE };
enum { FILT_LP, FILT_BP, FILT_HP };

struct env_patch {
    uint32_t a_us, d_us, r_us;
    uint16_t s_q16; /* 0..65535 (65536 is clipped to 65535) */
};

struct patch {
    uint8_t wave1, wave2;
    uint16_t pw_q16;            /* pulse width, 32768 = 50 % */
    int32_t detune_cents;       /* osc2 relative to osc1 */
    int32_t osc2_semis;         /* osc2 transpose */
    uint32_t g1, g2, gn;        /* mix, Q16 */
    uint32_t cutoff_hz;
    uint32_t res_x100;          /* resonance Q * 100 */
    uint8_t fmode;
    int32_t env2_cents;         /* ADSR2 -> cutoff depth */
    int32_t vel_cut_cents;      /* velocity -> cutoff (at velocity 127) */
    uint32_t vel_amp_depth;     /* Q16: 0 = no velocity, 65536 = full */
    uint32_t master;            /* Q16 */
    uint8_t bend_semis;
    struct env_patch env1, env2;
};

struct synth {
    struct voice_alloc va;
    struct fs_info fs;
    uint32_t p_a4;
    int nvoices;
    struct patch p;
    uint8_t retrig[VA_MAX_VOICES]; /* retrigger toggle bit per voice */
    uint8_t mod_wheel;
    int16_t bend;
};

extern const struct patch default_patch;

void hw_write(uint32_t addr, uint32_t val);
uint32_t hw_read(uint32_t addr);

void synth_init(struct synth *s, int nvoices, struct fs_info fs, const struct patch *p);
void synth_apply_patch(struct synth *s);
/* one event from the MIDI FIFO (status, d1, d2); returns the voice touched or -1 */
int synth_midi(struct synth *s, uint8_t st, uint8_t d1, uint8_t d2);
void synth_all_off(struct synth *s);

#endif
