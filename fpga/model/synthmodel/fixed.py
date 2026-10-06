"""Fixed-point conventions shared by RTL and models.

Audio samples: Q2.16 in DATA_W = 18 bits, 1.0 = 2**16 = machine unit (МЕ, +-10 V).
DAC full scale (+-12.5 V) = 1.25 МЕ: dac_code = sat(x * DAC_GAIN >> 16), DAC_GAIN = 1.6 * 2**16.
Pitch: unsigned PITCH_W = 21 bits = log2(phase_inc) * 2**16 (oct = [20:16], frac = [15:0]).
"""

DATA_W = 18
FRAC = 16
ONE = 1 << FRAC
DAC_GAIN = 104858  # round(1.6 * 2**16): 1.0 МЕ -> 0.8 of the DAC full scale
PITCH_W = 21
PITCH_FRAC = 16


def sat(x: int, bits: int = DATA_W) -> int:
    lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return lo if x < lo else hi if x > hi else x


def to_dac(x: int, data_w: int = DATA_W) -> int:
    """Q2.16 sample -> DAC code (same data_w), saturated. Arithmetic shift = floor."""
    return sat((x * DAC_GAIN) >> 16, data_w)


def sat_u(x: int, bits: int) -> int:
    return 0 if x < 0 else min(x, (1 << bits) - 1)
