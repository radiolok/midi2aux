from synthmodel import clocks


def test_default_fs_within_3_percent():
    half = clocks.bck_half(99_000_000, 48_000)
    assert half == 16
    fs = clocks.fs_actual(99_000_000, half)
    assert abs(fs / 48_000 - 1) < 0.03


def test_phase_inc_matches_fs():
    half = clocks.bck_half(99_000_000, 48_000)
    fs = clocks.fs_actual(99_000_000, half)
    inc = clocks.phase_inc(440, 99_000_000, half)
    assert abs(inc * fs / 2**32 / 440 - 1) < 1e-8
    assert inc == clocks.phase_inc_hz(440.0, fs)


def test_note_hz():
    assert clocks.note_hz(69) == 440.0
    assert abs(clocks.note_hz(81) - 880.0) < 1e-9
    assert abs(clocks.note_hz(60) - 261.6256) < 1e-3
