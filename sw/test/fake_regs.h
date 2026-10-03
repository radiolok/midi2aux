/* Fake register file for host tests: 64 KB banks by address bits [29:28] and [17:16]
 * (periph 0x1000_0000, voices/globals/mod 0x2000_0000.., bus/slots 0x3000_0000..). */
#ifndef FAKE_REGS_H
#define FAKE_REGS_H

#include <stdint.h>

static uint32_t regs[16 * 16384];
static uint32_t idx(uint32_t a) { return (((a >> 28) & 3) * 4 + ((a >> 16) & 3)) * 16384 + ((a & 0xFFFF) >> 2); }
void hw_write(uint32_t a, uint32_t v) { regs[idx(a)] = v; }
uint32_t hw_read(uint32_t a) { return regs[idx(a)]; }

#endif
