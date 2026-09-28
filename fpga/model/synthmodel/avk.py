"""Link with the AVK: input ADC calibration and decimation, the signal bus, slots, output mixer.
Bit-exact models of fpga/rtl/avk/*.sv. Samples Q2.16 (1.0 = machine unit = +-10 V).

ADC (AD7091R, 12 bit, 0..4095 = -12.5..+12.5 V) at 4 * fs:
    x = sat18(((code - OFFSET) * GAIN) >> 16)          OFFSET = 2048, GAIN = 40 << 16
FIR decimator 4:1, 64 taps c[k] (Q1.17, from `fir_taps()`), output every 4th input:
    y[n] = sat18((sum_k c[k] * x[4n + 3 - k]) >> 17)

Bus: S0 synth (sat18), S1 IN1, S2 IN2, S3 LFO1, S4 LFO2, S5 SYNC (+-1), S6 ENV, S7 GATE (0/1),
S8 + k: output of slot k. Slots run in order; a slot reading a later slot sees its previous sample.

MATH slot (TYPE_ID 1): PARAM0 = op, PARAM1 = k (Q2.16):
    0 A*B   1 A/B   2 |A|   3 A+B   4 A-B   5 min   6 max   7 A mod B   8 A*k+B   (all saturated)
Mixer: OUT  = softclip(sat21((sum_i GAIN_i * S_i) >> 16) + OUT_DC)
       OUT2 = softclip(sat21((S[SEL2] * GAIN2) >> 16) + OUT2_DC)
"""

import numpy as np
from scipy import signal

from .softclip import softclip

OSR = 4
FIR_TAPS = 64
ADC_OFFSET = 2048
ADC_GAIN = 40 << 16
BUS_FIXED = 8
S_SYNTH, S_IN1, S_IN2, S_LFO1, S_LFO2, S_SYNC, S_ENV, S_GATE = range(8)
MUL, DIV, ABS, ADD, SUB, MIN, MAX, MOD, AXPB = range(9)
TYPE_MATH = 1


def sat(x, bits):
    lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return lo if x < lo else hi if x > hi else x


def fir_taps(fs_in=99e6 / 512):
    h = signal.firwin(FIR_TAPS, 21500, fs=fs_in, window=("kaiser", 7))
    return [int(round(v * (1 << 17))) for v in h]


def adc_to_q16(code, offset=ADC_OFFSET, gain=ADC_GAIN):
    return sat(((code - offset) * gain) >> 16, 18)


def volts_to_code(v):
    """Ideal front end: -12.5..+12.5 V -> 0..4095."""
    return int(np.clip(np.floor((v + 12.5) / 25.0 * 4096), 0, 4095))


class Decimator:
    def __init__(self, taps=None):
        self.c = taps or fir_taps()
        self.hist = [0] * FIR_TAPS  # hist[0] = newest
        self.phase = 0

    def push(self, x):
        """One input sample; returns an output every OSR inputs, else None."""
        self.hist = [x] + self.hist[:-1]
        self.phase += 1
        if self.phase < OSR:
            return None
        self.phase = 0
        return sat(sum(c * h for c, h in zip(self.c, self.hist)) >> 17, 18)


def trunc_div(a, b):
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def math_op(op, a, b, k=0):
    if op == MUL:
        return sat((a * b) >> 16, 18)
    if op == DIV:
        if b == 0:
            return (1 << 17) - 1 if a >= 0 else -(1 << 17)
        return sat(trunc_div(a << 16, b), 18)
    if op == ABS:
        return sat(abs(a), 18)
    if op == ADD:
        return sat(a + b, 18)
    if op == SUB:
        return sat(a - b, 18)
    if op == MIN:
        return min(a, b)
    if op == MAX:
        return max(a, b)
    if op == MOD:
        return a if b == 0 else a - b * trunc_div(a, b)
    if op == AXPB:
        return sat(((a * k) >> 16) + b, 18)
    return a


class Slot:
    def __init__(self, type_id=TYPE_MATH):
        self.type_id = type_id
        self.sel_a = S_IN1
        self.sel_b = S_IN2
        self.bypass = 0
        self.param = [0] * 16

    def run(self, a, b):
        if self.bypass:
            return a
        if self.type_id == TYPE_MATH:
            return math_op(self.param[0], a, b, sat(self.param[1], 18))
        return a


class AvkBus:
    def __init__(self, slot_types=(TYPE_MATH, TYPE_MATH)):
        self.slots = [Slot(t) for t in slot_types]
        self.n = BUS_FIXED + len(self.slots)
        self.s = [0] * self.n
        self.gain = [0] * self.n
        self.gain[S_SYNTH] = 1 << 16
        self.out_dc = self.out2_dc = 0
        self.sel2 = S_LFO1
        self.gain2 = 1 << 16

    def sample(self, synth, in1, in2, lfo1, lfo2, sync, env, gate):
        s = self.s
        s[:BUS_FIXED] = [sat(synth, 18), in1, in2, lfo1, lfo2, (1 << 16) if sync else -(1 << 16), env,
                         (1 << 16) if gate else 0]
        for k, sl in enumerate(self.slots):
            s[BUS_FIXED + k] = sl.run(s[sl.sel_a], s[sl.sel_b])
        acc = sum(g * v for g, v in zip(self.gain, s))
        out = softclip(sat(sat(acc >> 16, 21) + self.out_dc, 21))
        out2 = softclip(sat(sat((s[self.sel2] * self.gain2) >> 16, 21) + self.out2_dc, 21))
        return out, out2
