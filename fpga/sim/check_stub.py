#!/usr/bin/env python3
"""Checks of the stage 0 stub simulation (tb_stub_core output) -> pass/fail.

  - TB summary: I2S format, BCK timing, MIDI echo;
  - fs: equals sys_clk / (128 * bck_half) and within 3 % of the target;
  - left (sine): fundamental within +-0.5 % of the tone, THD, THD+N, amplitude;
  - right (saw): fundamental, 2nd harmonic at -6 dB;
  - both channels bit-exact with the Python NCO model (fpga/model/synthmodel/nco.py).
Writes PNG plots and a JSON report; exit code 1 if any check fails.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "model"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from synthmodel import analysis, clocks, nco, wavio  # noqa: E402

SETTLE_S = 0.01  # skip the start (zeros before the first NCO output)


class Checks:
    def __init__(self):
        self.rows = []

    def add(self, name, value, ok, limit):
        self.rows.append({"check": name, "value": value, "limit": limit, "ok": bool(ok)})

    @property
    def ok(self):
        return all(r["ok"] for r in self.rows)

    def print(self):
        for r in self.rows:
            v = r["value"]
            v = f"{v:.6g}" if isinstance(v, float) else str(v)
            print(f"  [{'PASS' if r['ok'] else 'FAIL'}] {r['check']:<28} {v:>16}   ({r['limit']})")


def align(rtl, ref, max_shift=16):
    """Shift s such that rtl[s + i] == ref[i] over the compared span, or None."""
    n = len(rtl) - max_shift
    for s in range(max_shift + 1):
        if np.array_equal(rtl[s:s + n], ref[:n]):
            return s
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--wav", type=Path, required=True)
    p.add_argument("--json", type=Path, required=True, help="tb_stub_core summary")
    p.add_argument("--out", type=Path, required=True, help="directory for plots and report")
    p.add_argument("--sys-clk", type=int, required=True)
    p.add_argument("--fs", type=int, default=48_000, help="target fs")
    p.add_argument("--tone", type=int, default=440)
    p.add_argument("--data-w", type=int, default=18)
    p.add_argument("--lut-aw", type=int, default=10)
    p.add_argument("--tol-pct", type=float, default=0.5)
    p.add_argument("--thd-max-db", type=float, default=-70.0)
    p.add_argument("--thdn-max-db", type=float, default=-60.0)
    a = p.parse_args()

    tb = json.loads(a.json.read_text())
    fs_wav, data, bits = wavio.read_wav(a.wav)
    fs = tb["fs_hz"]
    fsc = float(1 << (a.data_w - 1))
    left = data[:, 0] >> (bits - a.data_w)
    right = data[:, 1] >> (bits - a.data_w)

    c = Checks()
    c.add("tb: I2S/timing/MIDI", tb.get("first_error") or "ok", tb["ok"], "no errors")
    c.add("tb: MIDI bytes echoed", f"{tb['midi_received']}/{tb['midi_sent']}", tb["midi_ok"], "all")

    half = clocks.bck_half(a.sys_clk, a.fs)
    fs_exp = clocks.fs_actual(a.sys_clk, half)
    c.add("fs, Hz", fs, abs(fs / fs_exp - 1) < 1e-6, f"= {fs_exp:.3f}")
    c.add("fs deviation, %", 100 * (fs / a.fs - 1), abs(fs / a.fs - 1) <= 0.03, "|x| <= 3")

    skip = int(SETTLE_S * fs)
    xl, xr = left[skip:] / fsc, right[skip:] / fsc
    f_l = analysis.fundamental(xl, fs)
    f_r = analysis.fundamental(xr, fs)
    tol = a.tol_pct / 100
    c.add("L: tone, Hz", f_l, abs(f_l / a.tone - 1) <= tol, f"{a.tone} +-{a.tol_pct}%")
    thd = analysis.thd_db(xl, fs, f_l)
    thdn = analysis.thdn_db(xl, fs, f_l)
    c.add("L: THD, dB", thd, thd <= a.thd_max_db, f"<= {a.thd_max_db}")
    c.add("L: THD+N, dB", thdn, thdn <= a.thdn_max_db, f"<= {a.thdn_max_db}")
    peak = float(np.max(np.abs(xl)))
    c.add("L: peak, FS", peak, 0.99 <= peak <= 1.0, "0.99..1.0")
    c.add("R: saw tone, Hz", f_r, abs(f_r / a.tone - 1) <= tol, f"{a.tone} +-{a.tol_pct}%")
    h2 = analysis.harmonics_db(xr, fs, f_r, 2)[0]
    c.add("R: saw H2/H1, dB", h2, abs(h2 + 6.02) <= 1.0, "-6.02 +-1")

    inc = clocks.phase_inc(a.tone, a.sys_clk, half)
    ref_sine, ref_saw = nco.nco(inc, len(left), a.data_w, a.lut_aw)
    s = align(left, ref_sine)
    c.add("L == model (bit-exact)", "shift %s" % s, s is not None, "exact")
    s_r = align(right, ref_saw)
    c.add("R == model (bit-exact)", "shift %s" % s_r, s_r is not None and s_r == s, "exact, same shift")

    a.out.mkdir(parents=True, exist_ok=True)
    t = np.arange(len(left)) / fs
    fig, ax = plt.subplots(3, 1, figsize=(10, 9))
    n_show = int(3 * fs / a.tone) + skip
    ax[0].plot(t[skip:n_show] * 1e3, xl[:n_show - skip], label="L sine")
    ax[0].plot(t[skip:n_show] * 1e3, xr[:n_show - skip], label="R saw")
    ax[0].set(xlabel="t, ms", ylabel="FS", title=f"stub_core: I2S decoded, fs = {fs:.2f} Hz")
    ax[0].legend(loc="upper right")
    ax[0].grid(True)
    for axi, x, name in ((ax[1], xl, "L sine"), (ax[2], xr, "R saw")):
        fr, db = analysis.spectrum_db(x, fs)
        axi.plot(fr, db, lw=0.7)
        axi.set(xlabel="f, Hz", ylabel="dBFS", ylim=(-160, 5), xlim=(0, fs / 2), title=f"{name} spectrum")
        axi.grid(True)
    ax[1].text(0.99, 0.95, f"f0 = {f_l:.3f} Hz\nTHD = {thd:.1f} dB\nTHD+N = {thdn:.1f} dB",
               transform=ax[1].transAxes, ha="right", va="top", family="monospace")
    fig.tight_layout()
    fig.savefig(a.out / "stub_core.png", dpi=110)

    report = {"ok": c.ok, "checks": c.rows, "tb": tb}
    (a.out / "stub_core_report.json").write_text(json.dumps(report, indent=2))
    print(f"check_stub: {a.wav}")
    c.print()
    print("check_stub:", "PASS" if c.ok else "FAIL")
    return 0 if c.ok else 1


if __name__ == "__main__":
    sys.exit(main())
