"""Stage 6: link with the AVK -- inputs IN1/IN2 (AD7091R models), MATH slot, OUT2 source,
modulation from an input, SYNC period and note triggering (UART console)."""

import numpy as np

import plots
import vsys

UART_BAUD = 1_000_000
NV = 2
ME = 65536 * 1.6  # DAC codes per machine unit (10 V)


def core():
    sw = vsys.build_sw()
    return vsys.build("synth_core", {"UART_BAUD": UART_BAUD, "RESET_ADDR": 0, "RAM_INIT": sw / "fw.hex", "SIM_FAST": 1,
                                     "NUM_VOICES": NV}, defines=["SOC", f"UART_BAUD={UART_BAUD}"])


def console(*cmds):
    s = ["wait READY"]
    for c in cmds:
        s += [f"sendline {c}", "wait ok "]
    return s + ["sendline get master", "wait master ="]


def amp(x, fs, f):
    """Amplitude of the f component (Hann-weighted projection)."""
    w = np.hanning(len(x))
    e = np.exp(-2j * np.pi * f * np.arange(len(x)) / fs)
    return 2 * abs(np.sum(w * x * e)) / np.sum(w)


def peak_freq(x, fs, lo, hi):
    nfft = 1 << 20
    mag = np.abs(np.fft.rfft(x * np.hanning(len(x)), nfft))
    fr = np.fft.rfftfreq(nfft, 1 / fs)
    sel = np.flatnonzero((fr > lo) & (fr < hi))
    return fr[sel[np.argmax(mag[sel])]]


def test_ring_modulator_in1_x_in2():
    """IN1 (300 Hz, 5 V) x IN2 (1 kHz, 5 V) in slot 1 -> OUT: 700 and 1300 Hz at 0.125 МЕ each;
    OUT2 = IN1."""
    r = vsys.run(core(), "avk_ringmod", 0.4,
                 uart_script=console("set slot1op 1", "set slot1a 1", "set slot1b 2", "set fxmix 100",
                                     "set out2src 1"),
                 args=["--in1", "sine:300:5", "--in2", "sine:1000:5"])
    xl, xr = r.left / ME, r.right / ME
    a, b = r.index(0.1), r.index(0.4) - 1
    plots.timeline_plot(r.out_dir / "avk_ringmod.png", r.fs, [("OUT = IN1·IN2, МЕ", xl), ("OUT2 = IN1, МЕ", xr)],
                        "slot MATH (A*B): IN1 300 Hz 5 V × IN2 1 kHz 5 V", xlim=(0.1, 0.12))
    l, rr = xl[a:b], xr[a:b]
    for f in (700, 1300):
        assert abs(amp(l, r.fs, f) - 0.125) < 0.004, f
    for f in (300, 1000):
        assert amp(l, r.fs, f) < 0.002, f
    assert abs(amp(rr, r.fs, 300) - 0.5) < 0.01
    assert amp(rr, r.fs, 1000) < 0.002


def test_input_modulates_pitch_and_out2_gate():
    """Route IN1 -> pitch, 1 МЕ = 1 octave; IN1 = +5 V: A4 sounds half an octave higher.
    OUT2 = GATE: 1 МЕ while the key is held."""
    events = [(140, [0x90, 69, 100]), (400, [0x80, 69, 0])]
    stim = vsys.write_midi(vsys.BUILD / "avk_fm_midi.txt", events)
    script = console("set out2src 7", "set mix2 0", "set cutoff 16000", "set vibrato 0")
    script[-2:-2] = ["sendline route 1 4 0 1 65536", "wait ok route 1"]
    r = vsys.run(core(), "avk_fm_gate", 0.5, midi=stim, uart_script=script, args=["--in1", "dc:5"])
    xl, xr = r.left / ME, r.right / ME
    plots.timeline_plot(r.out_dir / "avk_fm_gate.png", r.fs, [("OUT, МЕ", xl), ("OUT2 = GATE, МЕ", xr)],
                        "IN1 = +5 V -> pitch (+1/2 octave); OUT2 = GATE")
    f = peak_freq(xl[r.index(0.2):r.index(0.39)], r.fs, 500, 800)
    # ADC code for +5 V: 2867 -> (2867 - 2048) * 40 / 65536 = 0.49988 octave
    expect = 440 * 2 ** ((2867 - 2048) * 40 / 65536)
    assert abs(f / expect - 1) < 0.002, (f, expect)
    on, off = xr[r.index(0.15):r.index(0.39)], xr[r.index(0.41):]
    assert np.all(np.abs(on - 1) < 1e-4) and np.all(off == 0)
    assert np.all(xr[r.index(0.08):r.index(0.139)] == 0)  # before: OUT2 = LFO1 until the console sets it


def test_sync_period_and_note_trigger():
    """SYNC 100 Hz square: the console shows the frequency; SYNC_NOTE mode plays note 60 on edges."""
    script = console("set syncmode 2", "set mix2 0", "set cutoff 16000", "set vibrato 0")
    script += ["sendline avk", "wait sync 100.00 Hz edges"]
    r = vsys.run(core(), "avk_sync", 0.3, uart_script=script, args=["--sync", "square:100:5"])
    x = r.left / ME
    plots.timeline_plot(r.out_dir / "avk_sync.png", r.fs, [("OUT, МЕ", x)],
                        "SYNC 100 Hz, mode note: note 60 retriggered on each rising edge")
    seg = x[r.index(0.15):r.index(0.3) - 1]
    assert np.max(np.abs(seg)) > 0.05
    f = peak_freq(seg, r.fs, 200, 330)
    assert abs(f / 261.626 - 1) < 0.003, f
