"""Log-domain pitch -> NCO phase increment. Bit-exact with fpga/rtl/audio/pitch2inc.sv.

pitch P = log2(phase_inc) * 2**16 (unsigned, 21 bits). Conversion:
    oct = P >> 16, idx = (P >> 6) & 1023, f6 = P & 63
    mant = T[idx] + ((D[idx] * f6) >> 6)            (Q1.17, 1.0..2.0)
    inc  = (mant << oct) >> 17
T[i] = round(2**17 * 2**(i/1024)), D[i] = T[i+1] - T[i] (T[1024] = 2**18).
"""

import math

from .fixed import PITCH_FRAC

EXP_AW = 10
MANT_FRAC = 17
SEMITONE_MUL = 349525  # 2**16 / 12 * 2**6, so semitone offset = (n * 349525) >> 6


def exp_table():
    n = 1 << EXP_AW
    t = [round((1 << MANT_FRAC) * 2.0 ** (i / n)) for i in range(n + 1)]
    return t[:n], [t[i + 1] - t[i] for i in range(n)]


_T, _D = exp_table()


def pitch2inc(p: int) -> int:
    oct_ = p >> PITCH_FRAC
    idx = (p >> (PITCH_FRAC - EXP_AW)) & ((1 << EXP_AW) - 1)
    f = p & ((1 << (PITCH_FRAC - EXP_AW)) - 1)
    mant = _T[idx] + ((_D[idx] * f) >> (PITCH_FRAC - EXP_AW))
    return ((mant << oct_) >> MANT_FRAC) & 0xFFFFFFFF


def log2_q16(x: int) -> int:
    """floor(log2(x) * 2**16) by repeated squaring (integer only, same as the SV function)."""
    assert x > 0
    msb = x.bit_length() - 1
    y = (x << 30) >> msb  # Q1.30 in [1, 2)
    r = msb
    for _ in range(16):
        y = (y * y) >> 30
        r <<= 1
        if y >= 2 << 30:
            y >>= 1
            r |= 1
    return r


def inc_for_hz(freq_hz_num: int, sys_clk_hz: int, bck_half: int) -> int:
    """round(f * 2**32 / fs) for integer f, fs = sys_clk / (128 * bck_half)."""
    return ((freq_hz_num << 32) * 128 * bck_half + sys_clk_hz // 2) // sys_clk_hz


def note_pitch(note: int, p_a4: int) -> int:
    return p_a4 + (((note - 69) * SEMITONE_MUL) >> 6)


def pitch_hz(p: int, fs_hz: float) -> float:
    return fs_hz * 2.0 ** (p / (1 << PITCH_FRAC) - 32)


def hz_pitch(f_hz: float, fs_hz: float) -> int:
    return int(round((math.log2(f_hz / fs_hz) + 32) * (1 << PITCH_FRAC)))
