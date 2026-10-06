"""Stage 0: stub_core sine/saw -> I2S -> WAV; format, MIDI echo, tone, bit-exact NCO."""

import json

import numpy as np

import plots
import vsys
from synthmodel import analysis, clocks, nco

TONE, FS_TARGET, DATA_W, LUT_AW = 440, 48_000, 18, 10
MIDI = vsys.ROOT / "fpga" / "sim" / "stimuli" / "stub_midi.txt"


def align(rtl, ref, max_shift=16):
    n = len(rtl) - max_shift
    for s in range(max_shift + 1):
        if np.array_equal(rtl[s:s + n], ref[:n]):
            return s
    return None


def test_stub_core():
    exe = vsys.build("stub_core", {"TONE_HZ": TONE}, defines=["MIDI_ECHO"])
    r = vsys.run(exe, "stub_core", 0.3, midi=MIDI)
    assert r.tb["midi_ok"] and r.tb["midi_sent"] == 22

    half = clocks.bck_half(vsys.SYS_CLK_HZ, FS_TARGET)
    fs_exp = clocks.fs_actual(vsys.SYS_CLK_HZ, half)
    assert abs(r.fs / fs_exp - 1) < 1e-6
    assert abs(r.fs / FS_TARGET - 1) <= 0.03

    skip = int(0.01 * r.fs)
    fsc = float(1 << (DATA_W - 1))
    xl, xr = r.left[skip:] / fsc, r.right[skip:] / fsc
    f_l, f_r = analysis.fundamental(xl, r.fs), analysis.fundamental(xr, r.fs)
    thd, thdn = analysis.thd_db(xl, r.fs, f_l), analysis.thdn_db(xl, r.fs, f_l)
    h2 = analysis.harmonics_db(xr, r.fs, f_r, 2)[0]
    report = {"f_left": f_l, "f_right": f_r, "thd_db": thd, "thdn_db": thdn, "saw_h2_db": h2}
    (r.out_dir / "report.json").write_text(json.dumps(report, indent=2))
    plots.tone_plot(r.out_dir / "stub_core.png", xl, xr, r.fs, TONE, f"stub_core: I2S decoded, fs = {r.fs:.2f} Hz",
                    f"f0 = {f_l:.3f} Hz\nTHD = {thd:.1f} dB\nTHD+N = {thdn:.1f} dB")

    assert abs(f_l / TONE - 1) <= 0.005
    assert abs(f_r / TONE - 1) <= 0.005
    assert thd <= -70
    assert thdn <= -60
    assert 0.99 <= np.max(np.abs(xl)) <= 1.0
    assert abs(h2 + 6.02) <= 1.0

    inc = clocks.phase_inc(TONE, vsys.SYS_CLK_HZ, half)
    ref_sine, ref_saw = nco.nco(inc, len(r.left), DATA_W, LUT_AW)
    s = align(r.left, ref_sine)
    assert s is not None, "left != model"
    assert align(r.right, ref_saw) == s, "right != model"
