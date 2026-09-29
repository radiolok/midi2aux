/* Presets: synth parameters + modulation routes 1..7 as a small binary record
 *   "AVKP" u16 version, u16 count, count x {u16 name hash, i16 value}, 7 x {src, via, dst, 0, i32 depth}
 * (little endian). Values are keyed by a hash of the parameter's console name, so presets survive
 * parameters being added or removed; unknown entries are skipped. */
#ifndef PRESET_H_INCLUDED
#define PRESET_H_INCLUDED

#include <stdint.h>

#include "synth.h"

#define PRESET_MAX_BYTES (8 + 4 * P_COUNT + 8 * (MOD_ROUTES - 1))

uint16_t preset_hash(const char *name);
int preset_pack(const struct synth *s, uint8_t *buf);                 /* returns the size */
/* applies a record; returns the number of values used or -1 if it is not a preset */
int preset_unpack(struct synth *s, const uint8_t *buf, int len);
void preset_name(int n, char out[13]);                                /* "PRESET07.BIN" */

#endif
