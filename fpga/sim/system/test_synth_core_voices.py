"""Stage 3: synth_core + firmware: MIDI chords -> polyphonic voices -> I2S."""

import re

import numpy as np
from scipy.signal import get_window

import plots
import vsys

UART_BAUD = 1_000_000
NV = 4


def core():
    sw = vsys.build_sw()
    return vsys.build("synth_core", {"UART_BAUD": UART_BAUD, "RESET_ADDR": 0, "RAM_INIT": sw / "fw.hex", "SIM_FAST": 1,
                                     "NUM_VOICES": NV}, defines=["SOC", f"UART_BAUD={UART_BAUD}"])


def hz(n, bend=0.0):
    """Expected spectral peak: osc1 and osc2 (+7 cents, default patch) are not resolved,
    the peak lies between them."""
    return 440 * 2 ** ((n - 69 + bend) / 12 + 3.5 / 1200)


def peak_near(x, fs, f, tol=0.01):
    """Peak frequency within f*(1 +- tol) and its level in dBFS (zero-padded spectrum)."""
    w = get_window("blackmanharris", len(x))
    nfft = 1 << 18
    mag = np.abs(np.fft.rfft((x - np.mean(x)) * w, nfft)) * 2 / np.sum(w)
    fr = np.fft.rfftfreq(nfft, 1 / fs)
    sel = np.flatnonzero((fr > f * (1 - tol)) & (fr < f * (1 + tol)))
    k = sel[np.argmax(mag[sel])]
    return fr[k], 20 * np.log10(mag[k] + 1e-12)


T0 = 100  # ms: the firmware is ready (display initialised) well before this
EVENTS = [(T0 + t, b, c) for t, b, c in [
    (5, [0x90, 60, 100], "C4"), (5.1, [0x90, 64, 100], "E4"), (5.2, [0x90, 67, 100], "G4"),
    (205, [0x80, 60, 0, 0x80, 64, 0, 0x80, 67, 0], "chord off"),
    (600, [0x90, 69, 127], "A4"), (700, [0xE0, 0x7F, 0x7F], "bend +2"),
    (850, [0xE0, 0x00, 0x40, 0x80, 69, 0], "bend 0, A4 off"),
    (1250, [0x90, 48, 90, 0x90, 52, 90, 0x90, 55, 90, 0x90, 59, 90, 0x90, 62, 90, 0x90, 65, 90], "6 notes"),
    (1450, [0xB0, 123, 0], "all notes off"),
]]


def test_polyphony():
    stim = vsys.write_midi(vsys.BUILD / "voices_midi.txt", EVENTS)
    r = vsys.run(core(), "synth_voices", 1.95, midi=stim, uart_script=[], stop_on="midi: b0 7b 00")
    fsc = 65536 * 1.6  # DAC code of 1.0 МЕ
    x = r.left / fsc
    plots.timeline_plot(r.out_dir / "synth_voices.png", r.fs, [("OUT, МЕ", x)],
                        "synth_core: chord, bend, voice stealing (4 voices)",
                        marks=[(e[0] / 1e3, e[2]) for e in EVENTS])
    log = r.uart
    assert "READY" in log and f"{NV} voices" in log

    # chord: all three fundamentals present, similar level
    seg = x[r.index(T0 / 1e3 + 0.05):r.index(T0 / 1e3 + 0.2)]
    levels = []
    for n in (60, 64, 67):
        f, db = peak_near(seg, r.fs, hz(n))
        assert abs(f / hz(n) - 1) < 2e-3, (n, f)
        levels.append(db)
    assert max(levels) - min(levels) < 3 and min(levels) > -30

    # release (300 ms, -60 dB) -> silence
    tail = x[r.index(T0 / 1e3 + 0.55):r.index(T0 / 1e3 + 0.59)]
    assert np.max(np.abs(tail)) < 1e-3

    # pitch bend +2 semitones
    f0, _ = peak_near(x[r.index(T0 / 1e3 + 0.62):r.index(T0 / 1e3 + 0.7)], r.fs, hz(69))
    f1, _ = peak_near(x[r.index(T0 / 1e3 + 0.72):r.index(T0 / 1e3 + 0.84)], r.fs, hz(69, 2))
    assert abs(f0 / hz(69) - 1) < 2e-3 and abs(f1 / hz(69, 2) - 1) < 2e-3

    # 6 notes on 4 voices: the last four sound (the two oldest were stolen). With the detuned
    # osc2 the fundamental beats (osc1/osc2 near antiphase cancel it), so a note counts as
    # present by its fundamental or 2nd harmonic.
    def note_db(seg, n):
        return max(peak_near(seg, r.fs, hz(n))[1], peak_near(seg, r.fs, 2 * hz(n))[1])

    vs = [int(v) for v in re.findall(r"midi: 90 (?:30|34|37|3b|3e|41) \w\w note_on ch=1 v=(\d)", log)]
    assert len(vs) == 6 and sorted(vs[:4]) == [0, 1, 2, 3] and vs[4:] == vs[:2]
    seg = x[r.index(T0 / 1e3 + 1.30):r.index(T0 / 1e3 + 1.44)]
    for n in (55, 59, 62, 65):
        assert note_db(seg, n) > -30, n
    for n in (48, 52):  # stolen: their fundamentals are gone (allocation itself is checked in the log)
        assert peak_near(seg, r.fs, hz(n))[1] < -45, n
