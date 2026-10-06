import numpy as np

from synthmodel import adsr

FS = 48_000


def test_segments():
    a, d, s, r = 0.01, 0.1, 0.5, 0.2
    n = int(0.8 * FS)
    gate = adsr.gate_signal(n, FS, [(0.0, 0.3)])
    env = adsr.adsr(gate, FS, a, d, s, r)
    peak = int(np.argmax(env))
    assert env[peak] == 1.0
    assert abs(peak / FS - a) < 2 / FS
    assert np.all(np.diff(env[:peak + 1]) > 0)
    k = int((a + d) * FS)
    assert abs(env[k] - s) < 1.1 * (1 - s) * adsr.DECAY_RATIO
    k = int((0.3 + r) * FS)
    assert env[k] < 1.1 * s * adsr.DECAY_RATIO
    assert env[-1] == 0.0


def test_retrigger_no_jump():
    gate = adsr.gate_signal(FS, FS, [(0.0, 0.2), (0.25, 0.5)])
    env = adsr.adsr(gate, FS, 0.005, 0.05, 0.7, 0.3)
    assert np.max(np.abs(np.diff(env))) < 0.05
    assert env[int(0.25 * FS) - 1] > 0.1  # still releasing when re-triggered


def test_long_times():
    gate = np.ones(FS, dtype=bool)
    env = adsr.adsr(gate, FS, 10.0, 10.0, 0.5, 10.0)
    assert 0 < env[-1] < 0.2
