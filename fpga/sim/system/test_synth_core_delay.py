"""Stage 7: DELAY slots in external memory (TB model with random latency), CPU memory window,
delay time from SYNC."""

import numpy as np

import plots
import vsys

UART_BAUD = 1_000_000
ME = 65536 * 1.6
MEM_WORDS = 16384
FS = 99e6 / 2048


def core():
    sw = vsys.build_sw()
    return vsys.build("synth_core", {"UART_BAUD": UART_BAUD, "RESET_ADDR": 0, "RAM_INIT": sw / "fw.hex", "SIM_FAST": 1,
                                     "NUM_VOICES": 2, "NUM_SLOTS": 4, "SLOT_TYPES": 0x02020101,
                                     "MEM_WORDS": MEM_WORDS},
                      defines=["SOC", f"UART_BAUD={UART_BAUD}"])


def console(*cmds):
    s = ["wait READY"]
    for c in cmds:
        s += [f"sendline {c}", "wait ok "]
    return s + ["sendline get master", "wait master ="]


def lag(x, ref_seg, start, lo, hi):
    """Lag (samples, lo..hi) where x best matches ref_seg taken at `start`."""
    best, arg = -1.0, None
    for d in range(lo, hi + 1):
        seg = x[start + d:start + d + len(ref_seg)]
        c = float(np.dot(seg, ref_seg))
        if c > best:
            best, arg = c, d
    return arg


def rms(x):
    return float(np.sqrt(np.mean(x ** 2)))


def burst_events(t_ms=150, dur_ms=20):
    return [(t_ms, [0x90, 69, 127]), (t_ms + dur_ms, [0x80, 69, 0])]


BURST = ["set a1 1", "set d1 1", "set s1 100", "set r1 1", "set mix2 0", "set cutoff 16000", "set vibrato 0",
         "set velamp 0", "set master 50", "set fxmix 100"]


def test_echo_time_and_feedback():
    """Synth -> delay 1 (50 ms, feedback 50 %): echoes 50 ms apart, each half the previous one."""
    stim = vsys.write_midi(vsys.BUILD / "delay_midi.txt", burst_events())
    r = vsys.run(core(), "delay_echo", 0.4, midi=stim,
                 uart_script=console(*BURST, "set dly1src 0", "set dly1time 50", "set dly1fb 50",
                                     "set dly1lvl 100", "mem 100 -1234", "mem 100"),
                 args=["--xmem-words", str(MEM_WORDS), "--xmem-latency", "4"])
    assert "ok mem 100 = -1234\nok mem 100 = -1234" in r.uart  # CPU window, shared with the slots
    x = r.left / ME
    plots.timeline_plot(r.out_dir / "delay_echo.png", r.fs, [("OUT, МЕ", x)],
                        "DELAY: 20 ms note, 50 ms, feedback 50 %", xlim=(0.13, 0.4))
    t_samp = round(50e-3 * FS)
    a = r.index(0.150)
    n = round(18e-3 * FS)
    orig = x[a:a + n]
    assert rms(orig) > 0.05
    d = lag(x, orig, a, t_samp - 40, t_samp + 40)
    assert d == t_samp, (d, t_samp)
    levels = [rms(x[a + k * t_samp:a + k * t_samp + n]) / rms(orig) for k in range(1, 5)]
    for k, lv in enumerate(levels):
        assert abs(lv - 0.5 ** k) < 0.03 + 0.05 * 0.5 ** k, levels
    gap = x[a + round(25e-3 * FS):a + round(45e-3 * FS)]  # between the note and the first echo
    assert np.max(np.abs(gap)) < 1e-3


def test_delay_time_from_sync():
    """dlysync on: SYNC 10 Hz sets the delay to 100 ms = 4834 samples."""
    stim = vsys.write_midi(vsys.BUILD / "delay_sync_midi.txt", burst_events(200))
    r = vsys.run(core(), "delay_sync", 0.36, midi=stim,
                 uart_script=console(*BURST, "set dly2src 0", "set dly2fb 0", "set dly2lvl 100", "set dlysync 1"),
                 args=["--xmem-words", str(MEM_WORDS), "--sync", "square:10:5"])
    x = r.left / ME
    t_samp = round(99e6 / 10 / 2048)
    a = r.index(0.200)
    orig = x[a:a + round(18e-3 * FS)]
    assert lag(x, orig, a, t_samp - 40, t_samp + 40) == t_samp
    assert abs(rms(x[a + t_samp:a + t_samp + len(orig)]) / rms(orig) - 1) < 0.03
