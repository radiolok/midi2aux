"""Stage 1: mono_core -- MIDI notes -> square wave at the right pitch, gate CV on R."""

import numpy as np

import plots
import vsys
from synthmodel import analysis, fixed

GATE_CODE = fixed.to_dac(fixed.ONE)
SQ_CODE = fixed.to_dac(fixed.ONE // 2)
LATENCY_MAX_MS = 3.0


def hz(note, bend_semi=0.0):
    return 440.0 * 2 ** ((note - 69 + bend_semi) / 12)


# (time_ms, bytes, comment); notes are held until the next event
EVENTS = [
    (10, [0x90, 69, 100], "A4 on"),
    (90, [0x80, 69, 0], "A4 off"),
    (110, [0x92, 60, 90], "C4 on, channel 3 (omni)"),
    (190, [72, 80], "C5 on, running status"),
    (270, [72, 0], "C5 off via vel 0, running status"),
    (290, [0x90, 45, 0xF8, 100], "A2 on with a clock byte inside"),
    (370, [0x90, 93, 127], "A6 on (legato: last note wins)"),
    (450, [0x80, 45, 64], "A2 off: not the sounding note, ignored"),
    (530, [0xE0, 0x7F, 0x7F], "bend +2 semitones"),
    (610, [0xE0, 0x00, 0x40], "bend centre"),
    (690, [0xB5, 123, 0], "All Notes Off"),
    (740, [0x90, 57, 64], "A3 on"),
    (800, [0xFC], "Stop"),
]
# (start_ms, end_ms, expected Hz) of sounding intervals, starting after the message ends
SOUNDING = [(10, 90, hz(69)), (110, 190, hz(60)), (190, 270, hz(72)), (290, 370, hz(45)),
            (370, 530, hz(93)), (530, 610, hz(93, 2)), (610, 690, hz(93)), (740, 800, hz(57))]


def test_mono_core():
    exe = vsys.build("mono_core")
    stim = vsys.write_midi(vsys.BUILD / "mono_core_midi.txt", EVENTS)
    r = vsys.run(exe, "mono_core", 0.85, midi=stim)
    fsc = float(1 << 17)
    plots.timeline_plot(r.out_dir / "mono_core.png", r.fs, [("L, FS", r.left / fsc), ("R gate, FS", r.right / fsc)],
                        "mono_core: MIDI -> square (L), gate CV (R)",
                        marks=[(e[0] / 1e3, e[2]) for e in EVENTS])

    gate = r.right == GATE_CODE
    assert np.all((r.right == 0) | gate), "R must be 0 or the gate CV"

    for start, end, f_exp in SOUNDING:
        msg_end = vsys.midi_end_ms(start, 4) / 1e3
        a, b = r.index(msg_end + 0.005), r.index(end / 1e3)
        seg = r.left[a:b]
        assert np.all(gate[a:b]), f"gate low in {start}..{end} ms"
        f = analysis.fundamental(seg / fsc, r.fs)
        assert abs(f / f_exp - 1) < 1e-3, f"{start} ms: {f:.3f} Hz, expected {f_exp:.3f}"
        assert set(np.unique(seg)) <= {SQ_CODE, fixed.to_dac(-(fixed.ONE // 2))}, "square amplitude"

    # silent (gate low, output ramped to zero) between notes and after Stop
    for t0, t1 in ((95, 108), (695, 738), (805, 840)):
        a, b = r.index(t0 / 1e3), r.index(t1 / 1e3)
        assert not np.any(gate[a:b]) and np.all(r.left[a + 200:b] == 0), f"not silent {t0}..{t1} ms"

    # latency: gate rises within LATENCY_MAX_MS after the Note On message ends
    for t in (10, 110, 740):
        end = vsys.midi_end_ms(t, 3) / 1e3
        i = r.index(end)
        rise = i + int(np.argmax(gate[i:]))
        lat_ms = (r.t(rise) - end) * 1e3
        assert 0 <= lat_ms <= LATENCY_MAX_MS, f"latency {lat_ms:.3f} ms"
