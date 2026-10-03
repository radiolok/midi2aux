"""NCO: phase accumulator + quarter-wave sine table. Bit-exact with fpga/rtl/audio/nco_sine.sv.

Output sample n (n = 0, 1, ...) is computed from phase (n + 1) * phase_inc mod 2**phase_w:
the accumulator is incremented on audio_tick before the table lookup.
"""

import numpy as np


def quarter_sine_table(data_w: int = 18, lut_aw: int = 10) -> np.ndarray:
    """rom[i] = round(A * sin(pi/2 * (i + 0.5) / N)), A = 2**(data_w-1) - 1.

    The half-step offset makes the mirrored quadrants symmetric, so the
    table never needs index N and the sine has no DC or even harmonics.
    """
    n = 1 << lut_aw
    amp = (1 << (data_w - 1)) - 1
    i = np.arange(n)
    return np.round(amp * np.sin(np.pi / 2 * (i + 0.5) / n)).astype(np.int64)


def phase_seq(phase_inc: int, n: int, phase_w: int = 32, phase0: int = 0) -> np.ndarray:
    """Accumulator values used for samples 0..n-1."""
    k = np.arange(1, n + 1, dtype=np.uint64)
    mask = np.uint64((1 << phase_w) - 1)
    return ((np.uint64(phase0) + np.uint64(phase_inc) * k) & mask).astype(np.int64)


def sine_int(phase: np.ndarray, data_w: int = 18, lut_aw: int = 10, phase_w: int = 32) -> np.ndarray:
    table = quarter_sine_table(data_w, lut_aw)
    n = 1 << lut_aw
    quad = (phase >> (phase_w - 2)) & 3
    addr = (phase >> (phase_w - 2 - lut_aw)) & (n - 1)
    addr = np.where(quad & 1, n - 1 - addr, addr)
    val = table[addr]
    return np.where(quad & 2, -val, val)


def saw_int(phase: np.ndarray, data_w: int = 18, phase_w: int = 32) -> np.ndarray:
    """Top data_w bits of the phase with inverted MSB, read as signed: -FS..+FS ramp."""
    return (phase >> (phase_w - data_w)) - (1 << (data_w - 1))


def nco(phase_inc: int, n: int, data_w: int = 18, lut_aw: int = 10, phase_w: int = 32):
    """(sine, saw) integer samples as produced by the RTL stub."""
    ph = phase_seq(phase_inc, n, phase_w)
    return sine_int(ph, data_w, lut_aw, phase_w), saw_int(ph, data_w, phase_w)


def osc_float(freq_hz: float, fs_hz: float, n: int, wave: str = "sine") -> np.ndarray:
    """Ideal (naive, non-bandlimited) oscillator in [-1, 1] for references."""
    ph = (freq_hz / fs_hz * np.arange(n)) % 1.0
    if wave == "sine":
        return np.sin(2 * np.pi * ph)
    if wave == "saw":
        return 2.0 * ph - 1.0
    if wave == "square":
        return np.where(ph < 0.5, 1.0, -1.0)
    if wave == "triangle":
        return 1.0 - 4.0 * np.abs(ph - 0.5)
    raise ValueError(f"unknown wave {wave!r}")
