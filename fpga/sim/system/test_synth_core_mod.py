"""Stage 4: LFO vibrato from the mod wheel, filter envelope, LFO -> cutoff route (UART console)."""

import numpy as np
from scipy.signal import get_window

import plots
import vsys

UART_BAUD = 1_000_000
NV = 2


def core():
    sw = vsys.build_sw()
    return vsys.build("synth_core", {"UART_BAUD": UART_BAUD, "RESET_ADDR": 0, "RAM_INIT": sw / "fw.hex",
                                     "NUM_VOICES": NV}, defines=["SOC", f"UART_BAUD={UART_BAUD}"])


def console(*cmds):
    s = ["wait READY"]
    for c in cmds:
        s += [f"sendline {c}", f"wait ok {c.split()[1]}"]
    return s + ["sendline get master", "wait master ="]


def track(x, fs, f0, frame=1024, hop=128, rel=0.1):
    """Frame-wise peak frequency near f0 (zero-padded FFT)."""
    w = get_window("blackmanharris", frame)
    nfft = 1 << 16
    fr = np.fft.rfftfreq(nfft, 1 / fs)
    sel = np.flatnonzero((fr > f0 * (1 - rel)) & (fr < f0 * (1 + rel)))
    out = []
    for i in range(0, len(x) - frame, hop):
        mag = np.abs(np.fft.rfft(x[i:i + frame] * w, nfft))
        out.append(fr[sel[np.argmax(mag[sel])]])
    return np.array(out), hop / fs


def centroid(x, fs):
    w = get_window("hann", len(x))
    mag = np.abs(np.fft.rfft(x * w))
    fr = np.fft.rfftfreq(len(x), 1 / fs)
    return float(np.sum(fr * mag) / np.sum(mag))


def test_vibrato_from_mod_wheel():
    events = [(40, [0x90, 69, 100]), (300, [0xB0, 1, 127]), (900, [0x80, 69, 0])]
    stim = vsys.write_midi(vsys.BUILD / "vibrato_midi.txt", events)
    r = vsys.run(core(), "synth_vibrato", 0.9, midi=stim,
                 uart_script=console("set mix2 0", "set cutoff 16000"))
    x = r.left / (65536 * 1.6)
    a = r.index(0.06)
    f, dt = track(x[a:r.index(0.88)], r.fs, 440)
    t = 0.06 + np.arange(len(f)) * dt
    plots.timeline_plot(r.out_dir / "synth_vibrato.png", 1 / dt, [("f, Hz", f)],
                        "vibrato: mod wheel 0 -> 127 at 0.3 s (LFO1 5.5 Hz, 50 cents)")
    before = f[(t > 0.1) & (t < 0.28)]
    after = f[t > 0.4]
    assert np.max(np.abs(before - 440)) < 1.2  # frame 21 ms: tracking resolution ~ 0.7 Hz
    dev = 440 * (2 ** (50 / 1200) - 1)
    assert 1.6 * dev < np.ptp(after) < 2.1 * dev
    spec = np.abs(np.fft.rfft((after - after.mean()) * np.hanning(len(after)), 1 << 14))
    rate = np.fft.rfftfreq(1 << 14, dt)[np.argmax(spec)]
    assert abs(rate - 5.5) < 0.3


def test_filter_envelope_and_lfo_route():
    events = [(40, [0x90, 45, 127]), (700, [0x80, 45, 0])]
    stim = vsys.write_midi(vsys.BUILD / "fenv_midi.txt", events)
    r = vsys.run(core(), "synth_fenv", 0.75, midi=stim,
                 uart_script=console("set cutoff 150", "set env2amt 4800", "set a2 1", "set d2 400",
                                     "set s2 0", "set res 300", "set velcut 0"))
    x = r.left / (65536 * 1.6)
    early = centroid(x[r.index(0.045):r.index(0.075)], r.fs)
    late = centroid(x[r.index(0.5):r.index(0.65)], r.fs)
    plots.timeline_plot(r.out_dir / "synth_fenv.png", r.fs, [("OUT, МЕ", x)],
                        "filter envelope: cutoff 150 Hz + 4 octaves, D2 400 ms")
    assert early > 3 * late, (early, late)
