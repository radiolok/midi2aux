"""State-variable filters (float references). Both return (lp, bp, hp).

svf_tpt       -- zero-delay-feedback (TPT) SVF after A. Simper / V. Zavalishin:
                 stable for any fc < fs/2, exact response at fc (bilinear with prewarp).
svf_chamberlin -- classic Chamberlin SVF: two integrators, cheap in fixed point,
                 accurate only for fc << fs (roughly fc < fs/6), may blow up above.

fc may be a scalar or a per-sample array (modulated cutoff); q > 0 is the resonance
(peak gain at fc of lp and bp outputs), q = 0.707 is Butterworth.
"""

import numpy as np


def _per_sample(v, n):
    return np.broadcast_to(np.asarray(v, dtype=float), (n,))


def svf_tpt(x, fs_hz: float, fc, q):
    x = np.asarray(x, dtype=float)
    n = len(x)
    g = np.tan(np.pi * _per_sample(fc, n) / fs_hz)
    k = 1.0 / _per_sample(q, n)
    a1 = 1.0 / (1.0 + g * (g + k))
    a2 = g * a1
    a3 = g * a2
    lp, bp, hp = np.empty(n), np.empty(n), np.empty(n)
    ic1 = ic2 = 0.0
    for i in range(n):
        v3 = x[i] - ic2
        v1 = a1[i] * ic1 + a2[i] * v3
        v2 = ic2 + a2[i] * ic1 + a3[i] * v3
        ic1 = 2.0 * v1 - ic1
        ic2 = 2.0 * v2 - ic2
        lp[i], bp[i], hp[i] = v2, v1, x[i] - k[i] * v1 - v2
    return lp, bp, hp


def svf_chamberlin(x, fs_hz: float, fc, q):
    x = np.asarray(x, dtype=float)
    n = len(x)
    f = 2.0 * np.sin(np.pi * _per_sample(fc, n) / fs_hz)
    qi = 1.0 / _per_sample(q, n)
    lp, bp, hp = np.empty(n), np.empty(n), np.empty(n)
    low = band = 0.0
    for i in range(n):
        low += f[i] * band
        high = x[i] - low - qi[i] * band
        band += f[i] * high
        lp[i], bp[i], hp[i] = low, band, high
    return lp, bp, hp


def freq_response(filt, fs_hz: float, fc, q, n: int = 1 << 15):
    """Magnitude responses (freqs, |LP|, |BP|, |HP|) from the impulse response."""
    imp = np.zeros(n)
    imp[0] = 1.0
    outs = filt(imp, fs_hz, fc, q)
    freqs = np.fft.rfftfreq(n, 1.0 / fs_hz)
    return (freqs, *(np.abs(np.fft.rfft(o)) for o in outs))
