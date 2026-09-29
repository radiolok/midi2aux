/* Synth parameters: one table of descriptors drives the patch defaults, the UART console
 * and the panel menu (stage 5). Values are integers in display units. */
#ifndef PATCH_H
#define PATCH_H

#include <stdint.h>

/* P_SLOTn_*: the n-th MATH slot, P_SLOTn_OP: 0 off, 1 + MATH_*; P_DLYn_*: the n-th DELAY slot;
 * P_SYNC_MODE: SYNC_OFF / SYNC_LFO / SYNC_NOTE; P_DLY_SYNC: delay time = SYNC period */
enum { SYNC_OFF, SYNC_LFO, SYNC_NOTE };
#define OUT2_PITCH 12 /* P_OUT2_SRC: pitch CV of the last note, 1 V/octave, 0 V = C4 */
#define SLOT_PARAMS (P_SLOT2_OP - P_SLOT1_OP)
#define DLY_PARAMS  (P_DLY2_SRC - P_DLY1_SRC)

enum unit { U_NONE, U_ENUM, U_HZ, U_HZ100, U_MS, U_PCT, U_CENTS, U_SEMI, U_Q100, U_MS10 };

enum param_id {
    P_WAVE1, P_WAVE2, P_PW, P_DETUNE, P_OSC2_SEMI, P_MIX1, P_MIX2, P_NOISE,
    P_CUTOFF, P_RES, P_FMODE, P_ENV2_AMT, P_VEL_CUT, P_VEL_AMP,
    P_A1, P_D1, P_S1, P_R1, P_A2, P_D2, P_S2, P_R2,
    P_LFO1_RATE, P_LFO1_WAVE, P_LFO2_RATE, P_LFO2_WAVE, P_VIBRATO, P_BEND, P_MASTER, P_FX_MIX,
    P_IN1_MIX, P_IN2_MIX, P_OUT2_SRC, P_OUT2_GAIN, P_SYNC_MODE, P_SYNC_NOTE,
    P_SLOT1_OP, P_SLOT1_A, P_SLOT1_B, P_SLOT1_K, P_SLOT2_OP, P_SLOT2_A, P_SLOT2_B, P_SLOT2_K,
    P_DLY1_SRC, P_DLY1_TIME, P_DLY1_FB, P_DLY1_LVL, P_DLY2_SRC, P_DLY2_TIME, P_DLY2_FB, P_DLY2_LVL,
    P_DLY_SYNC,
    P_CHO_SRC, P_CHO_BASE, P_CHO_DEPTH, P_CHO_RATE, P_CHO_FB, P_CHO_LVL,
    P_REV_SRC, P_REV_ROOM, P_REV_DAMP, P_REV_LVL,
    P_HSYNC, P_FOLLOW_SRC, P_FOLLOW_ATK, P_FOLLOW_REL,
    P_COUNT
};

struct param_desc {
    const char *name;   /* console name (ASCII) */
    const char *label;  /* menu label (UTF-8, Russian) */
    int32_t min, max, def;
    uint8_t unit;
    const char *const *enum_names; /* U_ENUM */
};

extern const struct param_desc param_table[P_COUNT];

struct patch {
    int32_t v[P_COUNT];
};

void patch_defaults(struct patch *p);
int  param_find(const char *name);                 /* -1 if unknown */
int32_t param_clamp(int id, int32_t v);
/* "440 Hz", "saw", "35 %" ... into buf */
void param_format(int id, int32_t v, char *buf, int n);

#endif
