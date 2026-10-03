"""Plot helpers for system tests (PNG artifacts)."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from synthmodel import analysis  # noqa: E402


def tone_plot(path, xl, xr, fs, tone, title, note=""):
    fig, ax = plt.subplots(3, 1, figsize=(10, 9))
    n = int(3 * fs / tone)
    t = np.arange(n) / fs * 1e3
    ax[0].plot(t, xl[:n], label="L")
    ax[0].plot(t, xr[:n], label="R")
    ax[0].set(xlabel="t, ms", ylabel="FS", title=title)
    ax[0].legend(loc="upper right")
    for axi, x, name in ((ax[1], xl, "L"), (ax[2], xr, "R")):
        fr, db = analysis.spectrum_db(x, fs)
        axi.plot(fr, db, lw=0.7)
        axi.set(xlabel="f, Hz", ylabel="dBFS", ylim=(-160, 5), xlim=(0, fs / 2), title=f"{name} spectrum")
    if note:
        ax[1].text(0.99, 0.95, note, transform=ax[1].transAxes, ha="right", va="top", family="monospace")
    for a in ax:
        a.grid(True)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def timeline_plot(path, fs, channels, title, marks=(), xlim=None):
    """channels: [(label, array in FS units)], marks: [(t_s, label)]."""
    fig, ax = plt.subplots(len(channels), 1, figsize=(11, 2.6 * len(channels)), sharex=True)
    ax = np.atleast_1d(ax)
    for a, (label, x) in zip(ax, channels):
        a.plot(np.arange(len(x)) / fs, x, lw=0.6)
        a.set(ylabel=label)
        a.grid(True, alpha=0.4)
        for t, m in marks:
            a.axvline(t, color="gray", lw=0.5, ls="--")
    for t, m in marks:
        ax[0].text(t, ax[0].get_ylim()[1], m, rotation=90, va="top", fontsize=7)
    ax[0].set_title(title)
    ax[-1].set_xlabel("t, s")
    if xlim:
        ax[-1].set_xlim(*xlim)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
