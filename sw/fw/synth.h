/* Synth control: MIDI events -> voice allocation -> engine / modulation registers.
 * Register access goes through hw_write / hw_read so the logic is host-testable. */
#ifndef SYNTH_H
#define SYNTH_H

#include <stdint.h>

#include "params.h"
#include "patch.h"
#include "voice_alloc.h"

#define MOD_ROUTES 8
struct mod_route {
    uint8_t src, via, dst;
    int32_t depth; /* raw register value: pitch units (PM/CM) or Q16 (AM/PW) */
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
    struct mod_route routes[MOD_ROUTES];
};

void hw_write(uint32_t addr, uint32_t val);
uint32_t hw_read(uint32_t addr);

void synth_init(struct synth *s, int nvoices, struct fs_info fs);
void synth_apply_patch(struct synth *s);
void synth_set_param(struct synth *s, int id, int32_t value);
/* one event from the MIDI FIFO (status, d1, d2); returns the voice touched or -1 */
int synth_midi(struct synth *s, uint8_t st, uint8_t d1, uint8_t d2);
void synth_all_off(struct synth *s);
/* route 0 is the vibrato route (LFO1 x mod wheel -> pitch), routes 1..7 are free */
void synth_set_route(struct synth *s, int k, struct mod_route r);

#endif
