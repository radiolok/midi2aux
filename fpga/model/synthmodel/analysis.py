"""Spectrum measurements used by the simulation checks."""

import numpy as np
from scipy.signal import get_window

WINDOW = "blackmanharris"
LOBE_BINS = 6  # half-width of the Blackman-Harris main lobe with margin, in bins
ZERO_PAD = 8


def power_spectrum(x, fs_hz: float):
    """(freqs, power) of the windowed signal, no zero padding (for band sums)."""
    x = np.asarray(x, dtype=float)
    w = get_window(WINDOW, len(x))
    spec = np.fft.rfft((x - np.mean(x)) * w)
    return np.fft.rfftfreq(len(x), 1.0 / fs_hz), np.abs(spec) ** 2


def spectrum_db(x, fs_hz: float):
    """(freqs, dB) normalised so that a full-scale sine (amplitude 1.0) peaks at 0 dB."""
    x = np.asarray(x, dtype=float)
    w = get_window(WINDOW, len(x))
    mag = np.abs(np.fft.rfft(x * w)) * 2.0 / np.sum(w)
    return np.fft.rfftfreq(len(x), 1.0 / fs_hz), 20 * np.log10(np.maximum(mag, 1e-12))


def fundamental(x, fs_hz: float, fmin: float = 10.0) -> float:
    """Strongest spectral peak above fmin, zero-padded FFT + parabolic interpolation."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    w = get_window(WINDOW, n)
    nfft = ZERO_PAD * n
    mag = np.abs(np.fft.rfft((x - np.mean(x)) * w, nfft))
    k0 = int(np.ceil(fmin * nfft / fs_hz))
    k = k0 + int(np.argmax(mag[k0:]))
    if 0 < k < len(mag) - 1:
        a, b, c = np.log(mag[k - 1:k + 2] + 1e-300)
        k = k + 0.5 * (a - c) / (a - 2 * b + c)
    return k * fs_hz / nfft


def _alias(f: float, fs_hz: float) -> float:
    f = f % fs_hz
    return fs_hz - f if f > fs_hz / 2 else f


def _band_power(freqs, power, f: float) -> float:
    df = freqs[1] - freqs[0]
    k = int(round(f / df))
    return float(np.sum(power[max(k - LOBE_BINS, 0):k + LOBE_BINS + 1]))


def harmonics_db(x, fs_hz: float, f0: float, n_harm: int = 10):
    """Levels of harmonics 2..n_harm relative to the fundamental, dB (aliases folded)."""
    freqs, power = power_spectrum(x, fs_hz)
    p1 = _band_power(freqs, power, f0)
    return [10 * np.log10(_band_power(freqs, power, _alias(h * f0, fs_hz)) / p1 + 1e-30)
            for h in range(2, n_harm + 1)]


def thd_db(x, fs_hz: float, f0: float, n_harm: int = 10) -> float:
    h = np.array(harmonics_db(x, fs_hz, f0, n_harm))
    return float(10 * np.log10(np.sum(10 ** (h / 10))))


def thdn_db(x, fs_hz: float, f0: float) -> float:
    """Everything except DC and the fundamental, relative to the fundamental."""
    freqs, power = power_spectrum(x, fs_hz)
    df = freqs[1] - freqs[0]
    k = int(round(f0 / df))
    fund = np.sum(power[k - LOBE_BINS:k + LOBE_BINS + 1])
    rest = np.sum(power[LOBE_BINS + 1:]) - fund
    return float(10 * np.log10(max(rest, 1e-30) / fund))
