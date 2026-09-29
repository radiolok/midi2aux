#!/usr/bin/env python3
"""Pictures for the top-level README.md: every signal comes from the bit-exact models
(synthmodel: voice engine, modulation unit, AVK bus and slots), the menu screenshots from the
firmware UI code itself (sw/tools/ui_pages.c on the host) drawn with the display font.

    python fpga/model/readme_figs.py            (make readme-img)   -> img/readme/*.png
"""

import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy import signal  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "fpga" / "model"))
sys.path.insert(0, str(ROOT / "fpga" / "sim" / "system"))

from synthmodel import avk, modunit, voice  # noqa: E402
from synthmodel.softclip import softclip  # noqa: E402
from synthmodel.voice import VoiceEngine, env_params  # noqa: E402

OUT = ROOT / "img" / "readme"
FS = 99e6 / 2048
ONE = 1 << 16

# reference palette (light): categorical slots in fixed order, text inks, surface
C1, C2, C3, C4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": INK2, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 1.6,
    "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold", "legend.frameon": False,
})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=110)
    plt.close(fig)
    print("wrote", OUT / name)


def t_ms(n):
    return np.arange(n) / FS * 1000


# ------------------------------------------------------------------ engine helpers
def engine(wave=voice.SAW, hz=110.0, cutoff=None, q=0.7, fmode=0, blep=0, g1=1 << 15, gn=0):
    e = VoiceEngine(1)
    g = e.g
    g.wave1, g.g1, g.g2, g.gn, g.blep, g.fmode = wave, g1, 0, gn, blep, fmode
    g.cutoff = voice.C_MAX if cutoff is None else voice.cutoff_pitch(cutoff, FS)
    g.res_q = voice.res_q(q) if cutoff is not None else 1 << 17
    g.env1 = env_params(0.001, 0.1, 1.0, 0.1, FS)
    r = e.regs[0]
    r.pitch1 = voice.cutoff_pitch(hz, FS)
    r.vel_amp, r.gate = ONE, 1
    return e


def run(e, n, skip=0):
    e.run(skip)
    return np.array(e.run(n), dtype=float) / ONE


# ------------------------------------------------------------------ oscillators
def fig_oscillators():
    ph = (np.arange(800) * (2 * (1 << 32) // 800)) & 0xFFFFFFFF
    fig, ax = plt.subplots(1, 5, figsize=(11, 2.2), sharey=True)
    items = [("Пила (saw)", voice.SAW, 32768), ("Меандр 50 %", voice.SQUARE, 32768),
             ("Импульс 25 % (PW)", voice.SQUARE, 16384), ("Треугольник", voice.TRI, 32768),
             ("Синус", voice.SINE, 32768)]
    for a, (title, w, pw) in zip(ax, items):
        a.plot(np.arange(800) / 400, [voice.wave(int(p), w, pw) / ONE for p in ph], color=C1)
        a.set_title(title)
        a.set_xlabel("периоды")
    ax[0].set_ylabel("МЕ")
    save(fig, "oscillators.png")


def fig_polyblep():
    fig = plt.figure(figsize=(11, 3.2))
    a0 = fig.add_subplot(1, 3, 1)
    specs = [fig.add_subplot(1, 3, 2), None]
    specs[1] = fig.add_subplot(1, 3, 3, sharey=specs[0])
    for i, (blep, col, lab) in enumerate(((0, C2, "без PolyBLEP"), (1, C1, "PolyBLEP"))):
        x = run(engine(voice.SAW, 3500.0, blep=blep), 1 << 14, skip=2000)
        f, p = signal.welch(x, FS, nperseg=4096)
        specs[i].plot(f / 1000, 10 * np.log10(p / p.max()), color=col, lw=0.8)
        specs[i].set(title=f"Спектр: {lab}", xlabel="кГц", ylim=(-100, 3))
        a0.plot(t_ms(60) * 1000, x[:60], color=col, marker="o", ms=3, label=lab)
    specs[0].set_ylabel("дБ")
    a0.set(title="Пила 3.5 кГц: отсчёты у скачка", xlabel="мкс", ylabel="МЕ")
    a0.legend(loc="lower center", bbox_to_anchor=(0.5, -0.45), ncol=2)
    save(fig, "polyblep.png")


def fig_hard_sync():
    fig, ax = plt.subplots(2, 1, figsize=(11, 3.6), sharex=True)
    n, period = round(0.025 * FS), round(FS / 100)
    for i, (hs, title) in enumerate(((0, "Генератор 440 Гц свободно"),
                                      (1, "Жёсткая синхронизация от СИНХР 100 Гц: форма повторяется каждые 10 мс"))):
        e = engine(voice.SAW, 440.0)
        e.g.hsync = hs
        e.run(500)
        x = np.array([e.sample(sync_edge=int(k % period == 0)) for k in range(n)], dtype=float) / ONE
        ax[i].plot(t_ms(n), x, color=C1)
        ax[i].set_title(title)
        for k in range(0, n, period):
            ax[i].axvline(k / FS * 1000, color=C2, lw=1, ls="--")
    ax[1].set_xlabel("мс")
    save(fig, "hard_sync.png")


# ------------------------------------------------------------------ filter
def lfsr_noise(n):
    x, out = 1, []
    for _ in range(n):
        x = voice.lfsr_step(x)
        out.append((x >> 15) - ONE)
    return np.array(out, dtype=float)


def fig_filter_response():
    n = 1 << 15
    fig, ax = plt.subplots(1, 3, figsize=(11, 3), sharey=True)
    ref = signal.welch(lfsr_noise(n + 400)[400:], FS, nperseg=2048)[1]
    for a, (mode, title) in zip(ax, ((0, "ФНЧ (lp)"), (1, "Полосовой (bp)"), (2, "ФВЧ (hp)"))):
        for q, col in ((0.7, C1), (4.0, C2)):
            x = run(engine(cutoff=1000.0, q=q, fmode=mode, g1=0, gn=ONE), n, skip=400)
            f, p = signal.welch(x * ONE, FS, nperseg=2048)
            a.semilogx(f[1:], 10 * np.log10(p[1:] / ref[1:]), color=col, label=f"Q = {q}")
        a.axvline(1000, color=INK2, lw=0.8, ls=":")
        a.set(title=f"{title}, срез 1 кГц", xlabel="Гц", xlim=(60, 20000), ylim=(-50, 20))
    ax[0].set_ylabel("дБ")
    ax[0].legend()
    save(fig, "filter_response.png")


def fig_filter_time():
    n = round(0.03 * FS)
    fig, ax = plt.subplots(1, 1, figsize=(11, 2.8))
    ax.plot(t_ms(n), run(engine(voice.SAW, 110.0), n, 2000), color=GRID, lw=2.5, label="пила 110 Гц без фильтра")
    ax.plot(t_ms(n), run(engine(voice.SAW, 110.0, cutoff=500.0, q=0.7), n, 2000), color=C1, label="ФНЧ 500 Гц, Q 0.7")
    ax.plot(t_ms(n), run(engine(voice.SAW, 110.0, cutoff=500.0, q=6.0), n, 2000), color=C2, label="ФНЧ 500 Гц, Q 6")
    ax.set(title="Фильтр во времени: срез сглаживает скачки, резонанс добавляет звон на срезе",
           xlabel="мс", ylabel="МЕ")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3)
    save(fig, "filter_time.png")


def fig_envelopes():
    e = engine(voice.SAW, 110.0, cutoff=150.0, q=2.0)
    g = e.g
    g.env1 = env_params(0.05, 0.15, 0.6, 0.25, FS)
    g.env2 = env_params(0.005, 0.3, 0.0, 0.2, FS)
    g.env2_depth = 4 * ONE  # +4 octaves at the peak
    r = e.regs[0]
    r.gate = 0
    e.run(10)
    n_on, n = round(0.45 * FS), round(0.8 * FS)
    env1, env2, out = [], [], []
    for k in range(n):
        r.gate = int(k < n_on)
        out.append(e.sample() / ONE)
        env1.append(e.st[0].e1 / (1 << 30))
        env2.append(e.st[0].e2 / (1 << 30))
    fig, ax = plt.subplots(2, 1, figsize=(11, 4.2), sharex=True)
    tt = np.arange(n) / FS
    ax[0].plot(tt, env1, color=C1, label="ADSR1 → громкость (A 50, D 150 мс, S 60 %, R 250 мс)")
    ax[0].plot(tt, env2, color=C2, label="ADSR2 → срез (A 5, D 300 мс, S 0)")
    ax[0].axvline(n_on / FS, color=INK2, lw=0.8, ls=":")
    ax[0].text(n_on / FS + 0.005, 0.3, "клавиша отпущена", color=INK2)
    ax[0].set(title="Огибающие", ylabel="уровень")
    ax[0].legend(loc="center right")
    ax[1].plot(tt, out, color=C1, lw=0.6)
    ax[1].set(title="Выход: пила 110 Гц через ФНЧ 150 Гц + 4 октавы от ADSR2 — «вау» в начале ноты",
              xlabel="с", ylabel="МЕ")
    save(fig, "envelopes.png")


# ------------------------------------------------------------------ modulation
def fig_lfo():
    names = ["синус", "треугольник", "пила вверх", "меандр", "случайный (S&H)", "пила вниз"]
    fig, ax = plt.subplots(1, 6, figsize=(11, 2), sharey=True)
    for w, a in enumerate(ax):
        m = modunit.ModUnit()
        per = 50 if w == 4 else 250  # S&H: a new value each period, show more of them
        m.lfo[0].inc, m.lfo[0].wave = (1 << 32) // per + 12345, w
        y = []
        for _ in range(500):
            m.step()
            y.append(m.lfo_out[0] / ONE)
        a.plot(np.arange(500) / per, y, color=C1, drawstyle="steps-post" if w == 4 else "default")
        a.set_title(names[w])
        a.set_xlabel("периоды")
    ax[0].set_ylabel("МЕ")
    save(fig, "lfo.png")


def fig_follower():
    n = round(0.6 * FS)
    amp = np.where(np.arange(n) < n / 3, 0.2, np.where(np.arange(n) < 2 * n / 3, 0.8, 0.3))
    x = (amp * np.sin(2 * np.pi * 200 * np.arange(n) / FS) * ONE).astype(int)
    m = modunit.ModUnit()
    m.follow_atk = round(ONE * (1 - np.exp(-1 / (0.005 * FS))))
    m.follow_rel = round(ONE * (1 - np.exp(-1 / (0.1 * FS))))
    f = []
    for v in x:
        m.step(in1=int(v))
        f.append(m.follow / ONE)
    fig, ax = plt.subplots(figsize=(11, 2.6))
    ax.plot(np.arange(n) / FS, x / ONE, color=GRID, lw=1, label="ВХ1")
    ax.plot(np.arange(n) / FS, f, color=C1, lw=2, label="детектор (атака 5 мс, спад 100 мс)")
    ax.set(title="Следящий детектор огибающей — источник модуляции 10", xlabel="с", ylabel="МЕ")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=2)
    save(fig, "follower.png")


# ------------------------------------------------------------------ AVK bus: MATH, clipper
def fig_math():
    t = np.linspace(0, 1, 600)
    a = (0.8 * np.sin(2 * np.pi * 2 * t) * ONE).astype(int)
    b = (0.6 * np.sin(2 * np.pi * 7 * t + 0.5) * ONE).astype(int)
    ops = [(avk.MUL, "A·B (кольцевой модулятор)"), (avk.ABS, "|A| (выпрямитель)"), (avk.MIN, "min(A, B)"),
           (avk.MAX, "max(A, B)"), (avk.ADD, "A + B"), (avk.AXPB, "A·k + B, k = −0.5")]
    fig, ax = plt.subplots(2, 3, figsize=(11, 4.4), sharex=True, sharey=True)
    for a_, (op, title) in zip(ax.flat, ops):
        y = [avk.math_op(op, int(p), int(q), -ONE // 2) / ONE for p, q in zip(a, b)]
        a_.plot(t, a / ONE, color=GRID, lw=2, label="A")
        a_.plot(t, b / ONE, color=GRID, lw=1, ls="--", label="B")
        a_.plot(t, y, color=C1, label="результат")
        a_.set_title(title)
    ax[0, 0].legend(loc="lower left", ncol=3, fontsize=8)
    for a_ in ax[1]:
        a_.set_xlabel("время")
    save(fig, "math.png")


def fig_softclip():
    x = np.linspace(-1.6, 1.6, 801)
    y = [softclip(int(v * ONE)) / ONE for v in x]
    t = np.linspace(0, 2, 400)
    s = 1.5 * np.sin(2 * np.pi * t)
    fig, ax = plt.subplots(1, 2, figsize=(11, 2.8))
    ax[0].plot(x, x, color=GRID, lw=2, label="без ограничения")
    ax[0].plot(x, y, color=C1, label="мягкий ограничитель")
    ax[0].set(title="Выходной ограничитель: линеен до 1 МЕ (10 В), затем плавно к 1.25 МЕ",
              xlabel="вход, МЕ", ylabel="выход, МЕ")
    ax[0].legend(loc="upper left")
    ax[1].plot(t, s, color=GRID, lw=2, label="сумма 1.5 МЕ")
    ax[1].plot(t, [softclip(int(v * ONE)) / ONE for v in s], color=C1, label="на выходе")
    ax[1].set(title="Перегрузка микшера не даёт жёсткой отсечки", xlabel="периоды")
    ax[1].legend(loc="upper right")
    save(fig, "softclip.png")


# ------------------------------------------------------------------ AVK bus: memory slots
def bus_with(slot_type, params, mem, n, x_of):
    m = avk.AvkBus((slot_type,), mem_words=mem)
    sl = m.slots[0]
    sl.sel_a, sl.mem_size = avk.S_IN1, mem
    for j, v in enumerate(params):
        sl.param[j] = v
    m.gain = [0] * m.n
    m.gain[avk.BUS_FIXED] = ONE
    y = []
    for k in range(n):
        m.sample(0, int(x_of(k)), 0, 0, 0, 0, 0, 0)
        y.append(m.s[avk.BUS_FIXED] / ONE)
    return np.array(y)


def burst(k, ms=20, hz=440):
    return 0.7 * ONE * np.sin(2 * np.pi * hz * k / FS) if k < ms * FS / 1000 else 0


def fig_delay():
    n = round(0.8 * FS)
    t = round(0.12 * FS)
    y = bus_with(avk.TYPE_DELAY, [t, ONE // 2, ONE, ONE], 1 << 16, n, burst)
    fig, ax = plt.subplots(figsize=(11, 2.6))
    ax.plot(np.arange(n) / FS, y, color=C1, lw=0.8)
    ax.set(title="Задержка 120 мс, повтор 50 %: каждое эхо вдвое тише (нота 20 мс на ВХ1)", xlabel="с", ylabel="МЕ")
    save(fig, "delay.png")


def fig_chorus():
    rate = 0.5
    inc = round(rate / FS * (1 << 32))
    base, depth = round(0.007 * FS), round(0.003 * FS)
    n = round(4 / rate * FS / 2)
    tt = np.arange(n) / FS
    ph = (np.arange(n) * inc) & 0xFFFFFFFF
    tri = np.where(ph >> 31, (~(ph >> 15)) & 0xFFFF, (ph >> 15) & 0xFFFF)
    dly = (base + depth * tri / ONE) / FS * 1000
    y = bus_with(avk.TYPE_CHORUS, [base, depth, inc, 0, ONE, ONE], 2048, n,
                 lambda k: 0.45 * ONE * np.sin(2 * np.pi * 440 * k / FS))
    env = np.sqrt(np.convolve(y ** 2, np.ones(480) / 480, mode="same"))
    fig, ax = plt.subplots(2, 1, figsize=(11, 3.8), sharex=True)
    ax[0].plot(tt, dly, color=C2)
    ax[0].set(title="Хорус: время задержки качается треугольником (7 ± 3 мс, 0.5 Гц)", ylabel="мс")
    ax[1].plot(tt, env, color=C1)
    ax[1].set(title="Синус 440 Гц + копия с плывущей задержкой: уровень «дышит» (биения)", xlabel="с",
              ylabel="СКЗ, МЕ")
    save(fig, "chorus.png")

    # flanger: short delay + feedback on noise -> moving comb (spectrogram)
    n = round(3 * FS)
    rng = np.random.default_rng(1)
    noise = rng.uniform(-0.3, 0.3, n) * ONE
    y = bus_with(avk.TYPE_CHORUS, [round(0.0005 * FS), round(0.004 * FS), round(0.25 / FS * (1 << 32)),
                                   round(0.7 * ONE), ONE // 2, ONE // 2], 2048, n, lambda k: noise[k])
    fig, ax = plt.subplots(figsize=(11, 3))
    ax.specgram(y, NFFT=1024, Fs=FS, noverlap=768, cmap="Blues", vmin=-120)
    ax.set(title="Флэнжер (задержка 0.5…4.5 мс, повтор 70 %) на шуме: гребёнка провалов ездит по спектру",
           xlabel="с", ylabel="Гц", ylim=(0, 8000))
    ax.grid(False)
    save(fig, "flanger.png")


def fig_reverb():
    n = round(1.6 * FS)
    fig, ax = plt.subplots(1, 2, figsize=(11, 3))
    for room, col in ((0.75, C1), (0.95, C2)):
        y = bus_with(avk.TYPE_REVERB, [round(room * ONE), round(0.2 * ONE), ONE, 0], 6000, n,
                     lambda k: ONE if k < 48 else 0)
        rms = np.sqrt(np.convolve(y ** 2, np.ones(480) / 480, mode="same"))
        ax[1].plot(np.arange(n) / FS, 20 * np.log10(rms + 1e-7), color=col, label=f"ROOM {room}")
        if room == 0.95:
            ax[0].plot(np.arange(round(0.25 * FS)) / FS * 1000, y[:round(0.25 * FS)], color=C1, lw=0.6)
    ax[0].set(title="Отклик на щелчок: отражения сгущаются", xlabel="мс", ylabel="МЕ")
    ax[1].set(title="Спад хвоста: размер помещения — длительность", xlabel="с", ylabel="дБ", ylim=(-100, -10))
    ax[1].legend()
    save(fig, "reverb.png")


# ------------------------------------------------------------------ menu screenshots
def fig_menu():
    import lcdimg
    exe = ROOT / "build" / "ui_pages"
    exe.parent.mkdir(exist_ok=True)
    sw = ROOT / "sw"
    subprocess.run(["gcc", "-std=c11", "-O1", "-I", sw / "include", "-I", sw / "fw", "-I", sw / "test",
                    sw / "tools" / "ui_pages.c", "-o", exe, "-lm"], check=True)
    pages, cur = {}, None
    for line in subprocess.run([exe], capture_output=True, text=True, check=True).stdout.splitlines():
        if line.startswith("page "):
            cur = line[5:]
            pages[cur] = []
        else:
            pages[cur].append(line.split("|", 1)[1].rsplit("|", 1)[0])
    font = lcdimg.load_font()
    rgb = {k: lcdimg.to_rgb(lcdimg.render_ui(v, font)) for k, v in pages.items()}
    import matplotlib.image as mpimg
    for k in ("0", "3", "knob"):
        mpimg.imsave(OUT / f"lcd_{k}.png", rgb[k].repeat(2, 0).repeat(2, 1))
    keys = [k for k in pages if k != "knob"]
    cols = 4
    rows = (len(keys) + cols - 1) // cols
    pad = 8
    sheet = np.full((rows * (135 + pad) + pad, cols * (240 + pad) + pad, 3), 0xFC, dtype=np.uint8)
    for i, k in enumerate(keys):
        y, x = pad + (i // cols) * (135 + pad), pad + (i % cols) * (240 + pad)
        sheet[y:y + 135, x:x + 240] = rgb[k]
    mpimg.imsave(OUT / "lcd_pages.png", sheet)
    print("wrote menu screenshots")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for f in (fig_oscillators, fig_polyblep, fig_hard_sync, fig_filter_response, fig_filter_time, fig_envelopes,
              fig_lfo, fig_follower, fig_math, fig_softclip, fig_delay, fig_chorus, fig_reverb, fig_menu):
        f()


if __name__ == "__main__":
    main()
