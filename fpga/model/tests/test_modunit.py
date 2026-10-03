import numpy as np

from synthmodel import analysis, modunit
from synthmodel.modunit import ModUnit, Route

FS = 48339.84


def lfo_inc(hz):
    return int(round(hz * 2**32 / FS))


def run_lfo(wave, hz=5.0, n=None):
    m = ModUnit()
    m.lfo[0].inc, m.lfo[0].wave = lfo_inc(hz), wave
    n = n or int(FS)
    out = []
    for _ in range(n):
        m.step()
        out.append(m.lfo_out[0])
    return np.array(out) / 65536


def test_lfo_waves_rate_and_range():
    for w in (modunit.SINE, modunit.TRI, modunit.SAW_UP, modunit.SQUARE, modunit.SAW_DOWN):
        x = run_lfo(w)
        assert -1.0 <= x.min() < -0.95 and 0.95 < x.max() <= 1.0, w
        assert abs(analysis.fundamental(x, FS, fmin=1.0) / 5.0 - 1) < 0.01, w
    s = run_lfo(modunit.SINE)
    ideal = np.sin(2 * np.pi * 5.0 * np.arange(1, len(s) + 1) / FS)
    assert np.max(np.abs(s - ideal)) < 0.06  # parabolic approximation


def test_random_changes_on_wrap_only():
    x = run_lfo(modunit.RANDOM, hz=10.0, n=int(FS))
    changes = np.count_nonzero(np.diff(x))
    assert 8 <= changes <= 10
    assert np.std(x) > 0.3


def test_matrix_vibrato_via_modwheel():
    m = ModUnit()
    m.lfo[0].inc = lfo_inc(5.0)
    m.routes[0] = Route(src=modunit.S_LFO1, via=modunit.S_MODWHEEL, dst=modunit.D_PM, depth=5461)
    pm = []
    for i in range(int(FS)):
        m.modwheel = 0 if i < FS / 2 else 65536
        pm.append(m.step()[0])
    pm = np.array(pm)
    assert np.all(pm[: int(FS / 2)] == 0)
    assert 5400 < pm.max() <= 5461 and -5461 <= pm.min() < -5400


def test_am_base_and_sums():
    m = ModUnit()
    m.am_base = 0
    m.aux = 32768
    m.routes[0] = Route(src=modunit.S_IN1, dst=modunit.D_AM, depth=65536)
    m.routes[1] = Route(src=modunit.S_AUX, dst=modunit.D_CM, depth=1 << 20)
    m.routes[2] = Route(src=modunit.S_AUX, dst=modunit.D_CM, depth=1 << 20)
    m.routes[3] = Route(src=modunit.S_GATE, dst=modunit.D_PW, depth=-16384)
    pm, cm, am, pw = m.step(in1=-30000, gate=1)
    assert am == -30000 and cm == 1 << 20 and pw == -16384 and pm == 0
    pm, cm, am, pw = m.step(in1=200000)
    assert am == 131071  # saturated


def test_sync_resets_phase():
    m = ModUnit()
    m.lfo[0].inc, m.lfo[0].sync_reset, m.lfo[0].wave = lfo_inc(3.0), 1, modunit.SAW_UP
    for _ in range(1000):
        m.step()
    m.step(sync_edge=1)
    assert m.lfo[0].phase == 0 and m.lfo_out[0] == -65536
