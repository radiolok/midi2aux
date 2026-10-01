"""Stage 8: CHORUS and REVERB slots in the whole core, hard sync from SYNC, envelope follower,
pitch CV on OUT2."""

import numpy as np

import plots
import vsys
from test_synth_core_avk import amp, peak_freq
from test_synth_core_delay import BURST, burst_events, rms

UART_BAUD = 1_000_000
ME = 65536 * 1.6
MEM_WORDS = 16384


def core():
    sw = vsys.build_sw()
    return vsys.build("synth_core", {"UART_BAUD": UART_BAUD, "RESET_ADDR": 0, "RAM_INIT": sw / "fw.hex", "SIM_FAST": 1,
                                     "NUM_VOICES": 2, "NUM_SLOTS": 6, "SLOT_TYPES": 0x040302020101,
                                     "MEM_WORDS": MEM_WORDS},
                      defines=["SOC", f"UART_BAUD={UART_BAUD}"])


def console(*cmds):
    s = ["wait READY"]
    for c in cmds:
        s += [f"sendline {c}", "wait ok "]
    return s + ["sendline get master", "wait master =", "sendline avk", "wait bus"]


def test_reverb_tail():
    stim = vsys.write_midi(vsys.BUILD / "reverb_midi.txt", burst_events())
    r = vsys.run(core(), "fx_reverb", 0.6, midi=stim,
                 uart_script=console(*BURST, "set revsrc 0", "set revroom 80", "set revdamp 30", "set revlvl 200"),
                 args=["--xmem-words", str(MEM_WORDS)])
    x = r.left / ME
    plots.timeline_plot(r.out_dir / "fx_reverb.png", r.fs, [("OUT, МЕ", x)],
                        "REVERB: 20 ms note, room 80 %, damp 30 %", xlim=(0.13, 0.6))
    a = r.index(0.15)
    note = rms(x[a:a + r.index(0.018) - r.index(0)])
    tail = [rms(x[r.index(t):r.index(t + 0.05)]) for t in (0.2, 0.3, 0.4, 0.5)]
    assert tail[0] > 0.02 * note, (note, tail)            # the reverb rings after the note
    assert tail[0] > tail[1] > tail[2] > tail[3], tail     # and decays
    # the dry path alone is silent after the note
    r2 = vsys.run(core(), "fx_reverb_dry", 0.3, midi=stim, uart_script=console(*BURST),
                  args=["--xmem-words", str(MEM_WORDS)])
    assert np.max(np.abs(r2.left[r2.index(0.2):])) == 0


def test_chorus_changes_the_sound():
    stim = vsys.write_midi(vsys.BUILD / "chorus_midi.txt", [(120, [0x90, 69, 127])])
    base = console(*BURST[:-3], "set s1 100")
    r0 = vsys.run(core(), "fx_chorus_off", 0.4, midi=stim, uart_script=base, args=["--xmem-words", str(MEM_WORDS)])
    r1 = vsys.run(core(), "fx_chorus", 0.4, midi=stim,
                  uart_script=base[:-4] + ["sendline set chosrc 0", "wait ok ", "sendline set cholvl 100",
                                           "wait ok ", "sendline set chorate 400", "wait ok ",
                                           "sendline set fxmix 100", "wait ok "] + base[-4:],
                  args=["--xmem-words", str(MEM_WORDS)])
    a, b = r0.index(0.2), r0.index(0.39)
    x0, x1 = r0.left[a:b] / ME, r1.left[a:b] / ME
    # dry + chorus: same pitch, the level beats as the delay moves (comb filtering)
    assert abs(peak_freq(x1, r1.fs, 400, 480) - 440) < 2
    w = round(10 * r0.fs / 440)  # 10 periods: no ripple from the window
    env = [rms(x1[i:i + w]) for i in range(0, len(x1) - w, w)]
    env0 = [rms(x0[i:i + w]) for i in range(0, len(x0) - w, w)]
    assert np.ptp(env0) < 0.02 * np.mean(env0)
    assert np.ptp(env) > 0.1 * np.mean(env)


def test_hard_sync_locks_to_sync():
    """Oscillator 440 Hz hard-synced by SYNC 100 Hz: the output repeats every 10 ms."""
    stim = vsys.write_midi(vsys.BUILD / "hsync_midi.txt", [(120, [0x90, 69, 127])])
    r = vsys.run(core(), "fx_hsync", 0.35, midi=stim,
                 uart_script=console(*BURST[:-3], "set s1 100", "set hsync 1"),
                 args=["--xmem-words", str(MEM_WORDS), "--sync", "square:100:5"])
    x = r.left[r.index(0.2):r.index(0.34)] / ME
    period = r.fs / 100
    # every SYNC edge restarts the phase: consecutive 10 ms periods are identical up to the edge
    # falling on a sample (483 or 484 samples apart)
    for k in range(10):
        a = round(k * period)
        best = min(rms(x[a:a + 400] - x[a + 483 + j:a + 883 + j]) for j in (-1, 0, 1, 2))
        assert best < 0.02 * rms(x), (k, best)
    # the spectrum is harmonic to 100 Hz: nothing left at the free-running 440 Hz
    assert amp(x, r.fs, 440) < 0.1 * max(amp(x, r.fs, 400), amp(x, r.fs, 500))


def test_follower_and_pitch_cv():
    """IN1 sine 5 V -> envelope follower -> pitch (+1 octave per МЕ); OUT2 = pitch CV of note 72."""
    stim = vsys.write_midi(vsys.BUILD / "follow_midi.txt", [(120, [0x90, 72, 127])])
    script = console(*BURST[:-3], "set s1 100", "set out2src 12")
    script[-4:-4] = ["sendline route 1 10 0 1 65536", "wait ok route 1"]
    r = vsys.run(core(), "fx_follow", 0.35, midi=stim, uart_script=script,
                 args=["--xmem-words", str(MEM_WORDS), "--in1", "sine:1000:5"])
    x = r.left[r.index(0.2):r.index(0.34)] / ME
    f = peak_freq(x, r.fs, 523.25 * 1.1, 523.25 * 1.6)
    # follower of |0.5 sin| with 5 ms attack, 100 ms release sits between the mean and the peak
    assert 523.25 * 2 ** 0.3 < f < 523.25 * 2 ** 0.5, f
    cv = r.right[r.index(0.15):] / ME
    assert np.all(np.abs(cv - 0.1) < 1e-4)  # +1 V
