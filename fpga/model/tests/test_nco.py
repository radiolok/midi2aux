import numpy as np

from synthmodel import analysis, clocks, luts, nco

FS = 48_000


def test_table_range_and_monotonic():
    t = nco.quarter_sine_table(18, 10)
    assert t.min() > 0 and t.max() <= 2**17 - 1
    assert np.all(np.diff(t) >= 0)


def test_sine_symmetry():
    ph = np.arange(0, 2**32, 2**20, dtype=np.int64)
    s = nco.sine_int(ph)
    # odd symmetry around half period: s(p + pi) == -s(p)
    assert np.array_equal(s[: len(s) // 2], -s[len(s) // 2:])
    assert abs(np.sum(s)) == 0


def test_sine_frequency_and_thd():
    inc = clocks.phase_inc_hz(440.0, FS)
    sine, saw = nco.nco(inc, FS // 2)
    x = sine / 2**17
    assert abs(analysis.fundamental(x, FS) / 440.0 - 1) < 1e-4
    assert analysis.thd_db(x, FS, 440.0) < -80
    assert analysis.thdn_db(x, FS, 440.0) < -65


def test_saw_ramp():
    inc = clocks.phase_inc_hz(1000.0, FS)
    _, saw = nco.nco(inc, 4800)
    assert saw.min() >= -(2**17) and saw.max() < 2**17
    h = analysis.harmonics_db(saw / 2**17, FS, 1000.0, 3)
    assert abs(h[0] - 20 * np.log10(0.5)) < 0.5


def test_generated_rom_up_to_date():
    assert luts.DEFAULT_ROM.read_text() == luts.sine_rom_sv(18, 10), "run `make luts`"
