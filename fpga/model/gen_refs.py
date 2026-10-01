#!/usr/bin/env python3
"""Reference WAVs and plots from the Python models (for listening and later RTL comparison).

    python gen_refs.py --out ../../build/model
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from synthmodel import adsr, clocks, nco, svf, wavio  # noqa: E402

SYS_CLK_HZ = 99_000_000
FS = clocks.fs_actual(SYS_CLK_HZ, clocks.bck_half(SYS_CLK_HZ, 48_000))
FS_WAV = int(round(FS))
DATA_W = 18


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=Path("../../build/model"))
    out = p.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    shift = 24 - DATA_W

    # NCO: bit-exact integer model of the RTL stub (sine L, saw R), 1 s
    n = FS_WAV
    sine, saw = nco.nco(clocks.phase_inc_hz(440.0, FS), n, DATA_W)
    wavio.write_wav(out / "nco_440.wav", FS_WAV, [sine << shift, saw << shift])

    # ADSR on a saw: two notes, the second re-triggers during release
    n = int(2.0 * FS)
    gate = adsr.gate_signal(n, FS, [(0.05, 0.6), (0.8, 1.3)])
    env = adsr.adsr(gate, FS, attack=0.02, decay=0.2, sustain=0.6, release=0.4)
    tone = nco.osc_float(220.0, FS, n, "saw")
    wavio.write_float(out / "adsr_saw_220.wav", FS_WAV, [0.8 * env * tone])

    # SVF: saw 110 Hz through a resonant low-pass, cutoff swept 100 Hz -> 8 kHz (exponential)
    n = int(3.0 * FS)
    fc = 100.0 * (80.0 ** (np.arange(n) / n))
    lp, bp, hp = svf.svf_tpt(0.5 * nco.osc_float(110.0, FS, n, "saw"), FS, fc, 4.0)
    wavio.write_float(out / "svf_sweep_lp_q4.wav", FS_WAV, [np.clip(lp / 2.5, -1, 1)])

    fig, ax = plt.subplots(3, 1, figsize=(10, 9))
    t = np.arange(len(env)) / FS
    ax[0].plot(t, env, label="env")
    ax[0].plot(t, gate, "--", lw=0.8, label="gate")
    ax[0].set(title="ADSR A=20 ms D=200 ms S=0.6 R=400 ms", xlabel="t, s")
    ax[0].legend()
    for i, (filt, name) in enumerate(((svf.svf_tpt, "TPT"), (svf.svf_chamberlin, "Chamberlin")), 1):
        for q in (0.707, 4.0):
            f, l_, b_, h_ = svf.freq_response(filt, FS, 1000.0, q)
            ax[i].semilogx(f[1:], 20 * np.log10(l_[1:]), label=f"LP q={q}")
            ax[i].semilogx(f[1:], 20 * np.log10(h_[1:]), "--", label=f"HP q={q}")
        ax[i].set(title=f"SVF {name}, fc = 1 kHz", xlabel="f, Hz", ylabel="dB", ylim=(-60, 20), xlim=(20, FS / 2))
        ax[i].legend(fontsize=8)
    for a_ in ax:
        a_.grid(True, which="both", alpha=0.4)
    fig.tight_layout()
    fig.savefig(out / "models.png", dpi=110)
    print(f"gen_refs: wrote reference WAVs and models.png to {out}")


if __name__ == "__main__":
    main()
