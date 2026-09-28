/* Musical parameters -> engine register values (integer / float, no libm).
 * Reference: fpga/model/synthmodel/voice.py and pitch.py; host tests: sw/test/test_params.c. */
#ifndef PARAMS_H
#define PARAMS_H

#include <stdint.h>

struct fs_info {
    uint32_t sys_clk;  /* Hz */
    uint32_t bck_half; /* fs = sys_clk / (128 * bck_half) */
};

uint32_t log2_q16(uint64_t x);                              /* floor(log2(x) * 2^16) */
uint32_t hz_pitch(const struct fs_info *fs, uint32_t hz);   /* log pitch of an integer frequency */
int32_t  note_pitch(uint32_t p_a4, int note);               /* equal temperament from A4 */
uint32_t cents_pitch(int32_t cents);                         /* pitch offset, may be negative */
uint32_t env_coef(const struct fs_info *fs, uint32_t time_us, int attack); /* {shift, mant} */
uint32_t res_damping(uint32_t q_x100);                       /* resonance Q * 100 -> 1/Q, Q2.16 */
uint32_t vel_amp(uint8_t vel, uint32_t depth_q16);           /* 1 - depth * (1 - (v/127)^2) */
float    fexp_neg(float x);                                   /* e^-x, x >= 0 */
uint32_t lfo_inc(const struct fs_info *fs, uint32_t hz_x100);   /* phase increment per sample */

#define PITCH_CUTOFF_MAX 1995158 /* engine clamp: fc = 0.34 fs */

#endif
