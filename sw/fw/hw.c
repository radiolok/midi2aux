/* Register access for synth.c (replaced by a fake in host tests). */
#include "hw.h"
#include "synth.h"

void hw_write(uint32_t addr, uint32_t val) { REG32(addr) = val; }
uint32_t hw_read(uint32_t addr) { return REG32(addr); }
