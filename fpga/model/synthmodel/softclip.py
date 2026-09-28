"""Soft clipper of the output: linear up to 1.0 МЕ, then a tanh knee to 1.25 МЕ (DAC full scale).
Bit-exact model of fpga/rtl/audio/softclip.sv. Samples Q.16 (1.0 = 65536).

    |x| <= T:  y = x                                 T = 1.0
    else:      u = (|x| - T) << 2   (units of (L - T) = 0.25, Q16), clamped to 4.0
               t = TANH[u >> 9] + ((DT[u >> 9] * (u & 511)) >> 9)
               y = sign(x) * (T + (t >> 2))
TANH[i] = round(tanh(i / 128) * 2^16), i = 0..512.
"""

import math

T = 1 << 16
L = 81920
U_MAX = 4 << 16


def tanh_table():
    t = [round(math.tanh(i / 128) * 65536) for i in range(513)]
    return t[:512], [t[i + 1] - t[i] for i in range(512)], t[512]


_T, _D, _LAST = tanh_table()


def softclip(x: int) -> int:
    a = -x if x < 0 else x
    if a <= T:
        return x
    u = (a - T) << 2
    if u >= U_MAX:
        t = _LAST
    else:
        i, fr = u >> 9, u & 511
        t = _T[i] + ((_D[i] * fr) >> 9)
    y = T + (t >> 2)
    return -y if x < 0 else y
