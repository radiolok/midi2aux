import numpy as np
import pytest

from synthmodel import svf

FS = 48_000


def _at(freqs, h, f):
    return h[int(round(f / (freqs[1] - freqs[0])))]


@pytest.mark.parametrize("q", [0.707, 5.0])
def test_tpt_response(q):
    fc = 1000.0
    freqs, lp, bp, hp = svf.freq_response(svf.svf_tpt, FS, fc, q)
    assert abs(lp[0] - 1.0) < 1e-3
    assert abs(_at(freqs, lp, fc) / q - 1) < 0.02
    assert abs(_at(freqs, bp, fc) / q - 1) < 0.02
    assert 20 * np.log10(_at(freqs, lp, 10 * fc)) < -38
    assert 20 * np.log10(_at(freqs, hp, fc / 10)) < -38
    assert abs(_at(freqs, hp, 20_000) - 1) < 0.05


def test_tpt_stable_near_nyquist():
    x = np.random.default_rng(1).standard_normal(4800)
    lp, bp, hp = svf.svf_tpt(x, FS, 20_000.0, 20.0)
    assert np.all(np.isfinite(lp)) and np.max(np.abs(lp)) < 1e3


def test_chamberlin_low_fc():
    fc, q = 500.0, 2.0
    freqs, lp, bp, hp = svf.freq_response(svf.svf_chamberlin, FS, fc, q)
    assert abs(lp[0] - 1.0) < 1e-3
    assert abs(_at(freqs, lp, fc) / q - 1) < 0.05
    assert 20 * np.log10(_at(freqs, lp, 10 * fc)) < -38


def test_modulated_cutoff():
    n = 4800
    x = np.ones(n)
    fc = np.linspace(100.0, 5000.0, n)
    lp, _, _ = svf.svf_tpt(x, FS, fc, 0.707)
    assert abs(lp[-1] - 1.0) < 1e-3
