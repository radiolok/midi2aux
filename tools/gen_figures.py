#!/usr/bin/env python3
"""Figures img/env-shapes.svg, img/env-times.svg, img/dds.svg.

Envelope curves use the same integer math as fw/src/envelope.cpp.
usage: python3 tools/gen_figures.py img
"""
import math, sys
from xml.sax.saxutils import escape

SURF = '#fcfcfb'; INK = '#0b0b0b'; INK2 = '#52514e'; MUTED = '#8a8984'
GRID = '#e6e5e1'; AXIS = '#b9b8b2'; HELD = '#f0efec'
C_PLUCK = '#2a78d6'; C_PAD = '#eb6834'; C_AQUA = '#1baf7a'
FONT = '-apple-system, Segoe UI, Helvetica, Arial, sans-serif'

# ---- envelope model: same integer math as fw/src/envelope.cpp
def params(pot):
    if pot < 128:
        x = pot / 127; atk = 2.0; dec = 50 * 60 ** x; rel = min(dec, 80.0); sus = 0
    else:
        y = (pot - 128) / 127; atk = 2 * 500 ** y; dec = rel = 50 * 40 ** y; sus = 1
    k = lambda ms: int(65536 * math.exp(-4.605 / ms))
    return dict(step=int(65535 / atk), dk=k(dec), rk=k(rel), sus=sus, atk=atk, dec=dec, rel=rel)

def simulate(pot, hold_ms, total_ms):
    p = params(pot); lvl = 0; st = 'A'; pts = [(0, 0)]
    for t in range(1, total_ms + 1):
        if t == hold_ms and st != 'I':
            st = 'R'
        if st == 'A':
            l = lvl + p['step']
            if l >= 0xFFFF:
                l = 0xFFFF; st = 'S' if p['sus'] else 'D'
            lvl = l
        elif st == 'D':
            lvl = lvl * p['dk'] >> 16
        elif st == 'R':
            lvl = lvl * p['rk'] >> 16
        if st in 'DR' and lvl < 256:
            lvl = 0; st = 'I'
        pts.append((t, (lvl >> 8) / 255))
    return pts

def fmt_ms(ms):
    return f'{ms/1000:g} s' if ms >= 1000 else f'{ms:g} ms'

class Svg:
    def __init__(self, w, h):
        self.w, self.h, self.o = w, h, [f'<rect width="{w}" height="{h}" fill="{SURF}"/>']
    def text(self, x, y, s, size=12, color=INK, anchor='start', weight=400, italic=False):
        st = ' font-style="italic"' if italic else ''
        self.o.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{color}" '
                      f'text-anchor="{anchor}" font-weight="{weight}"{st}>{escape(s)}</text>')
    def line(self, x1, y1, x2, y2, color=GRID, w=1, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ''
        self.o.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                      f'stroke="{color}" stroke-width="{w}"{d}/>')
    def rect(self, x, y, w, h, fill, rx=0):
        self.o.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}"/>')
    def path(self, pts, color, w=2, dash=None, fill=None):
        d = 'M' + ' L'.join(f'{x:.1f},{y:.1f}' for x, y in pts)
        da = f' stroke-dasharray="{dash}"' if dash else ''
        self.o.append(f'<path d="{d}" fill="{fill or "none"}" stroke="{color}" stroke-width="{w}" '
                      f'stroke-linejoin="round" stroke-linecap="round"{da}/>')
    def save(self, fn, title, desc):
        open(fn, 'w').write(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" font-family="{FONT}" role="img">\n'
            f'<title>{escape(title)}</title><desc>{escape(desc)}</desc>\n'
            + '\n'.join(self.o) + '\n</svg>\n')

def nice_ticks(tmax):
    for step in (50, 100, 200, 250, 500, 1000, 2000):
        if tmax / step <= 5:
            return [i * step for i in range(int(tmax // step) + 1)]

# ---- figure 1: envelope shape at six knob positions (small multiples)
def shapes(fn):
    W, H = 900, 560
    s = Svg(W, H)
    s.text(24, 34, 'Sine envelope at six knob positions', 16, weight=600)
    s.text(24, 54, 'Amplitude over time. Grey band = key held; dashed line = key released.', 12, INK2)
    panels = [  # pot, hold ms, window ms, label
        (0,   300, 400,  '0 %'),
        (64,  1000, 1200, '25 %'),
        (127, 1500, 2000, '50 % (left of centre)'),
        (128, 500,  800,  '50 % (right of centre)'),
        (192, 1000, 1600, '75 %'),
        (255, 2500, 5500, '100 %'),
    ]
    rows = [('Pluck / bell — fades out on its own, key-up damps it', C_PLUCK),
            ('Organ → pad — holds while pressed, attack and fade grow', C_PAD)]
    pw, ph, gx = 236, 150, 44
    x0s = [62, 62 + pw + gx, 62 + 2 * (pw + gx)]
    y0s = [110, 360]
    for i, (pot, hold, win, lab) in enumerate(panels):
        r, c = divmod(i, 3)
        color = rows[r][1]
        x0, y0 = x0s[c], y0s[r]
        if c == 0:
            s.text(24, y0 - 30, rows[r][0], 13, INK, weight=600)
        X = lambda t: x0 + t / win * pw
        Y = lambda a: y0 + ph - a * ph
        s.rect(X(0), y0, X(min(hold, win)) - X(0), ph, HELD)
        for a in (0.5, 1.0):
            s.line(x0, Y(a), x0 + pw, Y(a), GRID)
        s.line(x0, Y(0), x0 + pw, Y(0), AXIS)
        for t in nice_ticks(win):
            s.line(X(t), Y(0), X(t), Y(0) + 4, AXIS)
            s.text(X(t), Y(0) + 17, fmt_ms(t), 10.5, INK2, 'middle')
        if c == 0:
            for a, l in ((0, '0'), (0.5, '50 %'), (1.0, '100 %')):
                s.text(x0 - 8, Y(a) + 4, l, 10.5, INK2, 'end')
        if hold < win:
            s.line(X(hold), y0 - 2, X(hold), Y(0), MUTED, 1.2, '4 3')
        pts = simulate(pot, hold, win)
        s.path([(X(t), Y(a)) for t, a in pts], color, 2)
        p = params(pot)
        s.text(x0 + pw / 2, y0 - 10, f'knob {lab}', 12, INK, 'middle', 600)
        if pot < 128:
            info = f'attack {fmt_ms(p["atk"])} · decay {fmt_ms(round(p["dec"]))}'
        else:
            info = f'attack {fmt_ms(round(p["atk"]))} · release {fmt_ms(round(p["rel"]))}'
        s.text(x0 + pw / 2, Y(0) + 36, info, 11, INK2, 'middle')
    s.save(fn, 'Sine envelope at six knob positions',
           'Small multiples of the envelope amplitude over time for knob positions 0, 25, 50, 50, 75 and 100 percent.')

# ---- figure 2: times along the knob (log y)
def times(fn):
    W, H = 900, 420
    s = Svg(W, H)
    s.text(24, 34, 'Envelope times along the knob', 16, weight=600)
    s.text(24, 54, 'Time to full level (attack) and to −40 dB (decay, release). Log scale.', 12, INK2)
    x0, y0, pw, ph = 80, 96, 660, 250
    tmin, tmax = 1, 5000
    X = lambda pot: x0 + pot / 255 * pw
    Y = lambda ms: y0 + ph - (math.log10(ms) - math.log10(tmin)) / (math.log10(tmax) - math.log10(tmin)) * ph
    s.rect(X(0), y0, X(127.5) - X(0), ph, '#f5f8fd')
    s.rect(X(127.5), y0, X(255) - X(127.5), ph, '#fdf6f2')
    s.text(X(64), y0 + 18, 'pluck / bell', 12, C_PLUCK, 'middle', 600)
    s.text(X(64), y0 + 33, 'no sustain', 11, INK2, 'middle')
    s.text(X(192), y0 + 18, 'organ → pad', 12, '#c4501f', 'middle', 600)
    s.text(X(192), y0 + 33, 'sustain 100 % while held', 11, INK2, 'middle')
    for ms, l in ((1, '1 ms'), (10, '10 ms'), (100, '100 ms'), (1000, '1 s')):
        s.line(x0, Y(ms), x0 + pw, Y(ms), GRID)
        s.text(x0 - 8, Y(ms) + 4, l, 10.5, INK2, 'end')
    s.line(x0, y0 + ph, x0 + pw, y0 + ph, AXIS)
    s.line(X(127.5), y0, X(127.5), y0 + ph, MUTED, 1, '4 3')
    for pct in (0, 25, 50, 75, 100):
        s.line(X(pct * 2.55), y0 + ph, X(pct * 2.55), y0 + ph + 4, AXIS)
        s.text(X(pct * 2.55), y0 + ph + 18, f'{pct} %', 10.5, INK2, 'middle')
    s.text(x0 + pw / 2, y0 + ph + 38, 'knob position', 11, INK2, 'middle')
    lo = list(range(0, 128)); hi = list(range(128, 256))
    atk = lambda r: [(X(p), Y(params(p)['atk'])) for p in r]
    s.path(atk(lo), C_PLUCK, 2); s.path(atk(hi), C_PLUCK, 2)
    s.path([(X(p), Y(params(p)['dec'])) for p in lo], C_PAD, 2, '7 4')
    rel = lambda r: [(X(p), Y(params(p)['rel'])) for p in r]
    s.path(rel(lo), C_AQUA, 2, '2 4'); s.path(rel(hi), C_AQUA, 2, '2 4')
    # direct labels
    s.text(X(255) + 8, Y(params(255)['atk']) + 4, 'attack 1 s', 11.5, INK)
    s.text(X(255) + 8, Y(params(255)['rel']) + 4, 'release 2 s', 11.5, INK)
    s.text(X(70), Y(params(70)['dec']) + 20, 'decay (key held)', 11.5, INK, 'start')
    s.text(X(60), Y(80) + 16, 'release (key up) ≤ 80 ms', 11.5, INK, 'middle')
    s.text(X(60), Y(2) - 8, 'attack 2 ms', 11.5, INK, 'middle')
    # legend
    lx, ly = x0, H - 18
    for i, (col, dash, name) in enumerate(((C_PLUCK, None, 'attack'), (C_PAD, '7 4', 'decay while held'),
                                          (C_AQUA, '2 4', 'release after key-up'))):
        xx = lx + i * 190
        s.path([(xx, ly - 4), (xx + 28, ly - 4)], col, 2, dash)
        s.text(xx + 36, ly, name, 11.5, INK)
    s.save(fn, 'Envelope times along the knob',
           'Log-scale line chart: attack, decay and release times versus knob position. Left half pluck, right half organ to pad.')

C_BOX_MAIN = ('#ebe6f7', '#6b55a8'); C_BOX_ISR = ('#fdf0dc', '#c47f17')

def box(s, x, y, w, h, colors, title, sub):
    f, st = colors
    s.o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{f}" stroke="{st}" stroke-width="1.5"/>')
    s.text(x + w / 2, y + h / 2 - 3, title, 12, INK, 'middle', 600)
    s.text(x + w / 2, y + h / 2 + 13, sub, 10.5, INK2, 'middle')

def arrow(s, x1, y, x2):
    s.line(x1, y, x2 - 6, y, '#444c56', 1.4)
    s.o.append(f'<path d="M{x2-7},{y-4} L{x2},{y} L{x2-7},{y+4} z" fill="#444c56"/>')

def dds(fn):
    W, H = 900, 780
    s = Svg(W, H)
    s.text(24, 34, 'How a poly voice makes sound: DDS', 16, weight=600)
    s.text(24, 54, 'Direct digital synthesis at a fixed sample rate fs = 31.25 kHz (one sample every 32 µs).', 12, INK2)

    # --- block chain
    bw, bh, gap, by = 104, 54, 16, 104
    blocks = [
        (C_BOX_MAIN, 'MIDI note', 'Note On'),
        (C_BOX_MAIN, 'inc', 'f · 2²⁴ / fs'),
        (C_BOX_ISR, 'acc += inc', '24-bit, wraps'),
        (C_BOX_ISR, 'index', 'acc >> 16'),
        (C_BOX_ISR, 'wavetable[i]', '256 bytes, shared'),
        (C_BOX_ISR, '× envelope', 'sine mode only'),
        (C_BOX_ISR, 'Σ voices', '→ OCR2B'),
    ]
    xs = [24 + i * (bw + gap) for i in range(len(blocks))]
    for x, (c, t, sub) in zip(xs, blocks):
        box(s, x, by, bw, bh, c, t, sub)
    for i in range(len(xs) - 1):
        arrow(s, xs[i] + bw, by + bh / 2, xs[i + 1])
    s.text((xs[0] + xs[1] + bw) / 2, by - 12, 'main loop, once per Note On', 11.5, '#6b55a8', 'middle', 600)
    s.text((xs[2] + xs[6] + bw) / 2, by - 12, 'TIMER0_COMPA ISR, every sample, for each sounding voice', 11.5, '#a86a10', 'middle', 600)

    # --- signals: example voice f = 2500 Hz (12.5 samples per period), second voice a fifth up
    fs = 31250; n = 32
    def voice(f):
        inc = round(f * 2 ** 24 / fs); acc = 0; out = []
        for k in range(n):
            out.append((k, acc, (acc >> 16)))
            acc = (acc + inc) & 0xFFFFFF
        return inc, out
    table = [round((math.sin(i * math.pi / 128) + 1) * 31.5) for i in range(256)]   # AMP = 63 (4 voices, TOP 255)
    inc1, v1 = voice(2500); inc2, v2 = voice(3750)

    x0, pw = 92, 520
    X = lambda k: x0 + k / n * pw
    def frame(y0, ph, title, ylabels):
        s.text(24, y0 - 14, title, 12.5, INK, weight=600)
        for frac, lab in ylabels:
            yy = y0 + ph - frac * ph
            s.line(x0, yy, x0 + pw, yy, GRID if frac else AXIS)
            s.text(x0 - 8, yy + 4, lab, 10.5, INK2, 'end')
    def stairs(vals, Y, color, w=2):
        pts = []
        for k, v in enumerate(vals):
            pts += [(X(k), Y(v)), (X(k + 1), Y(v))]
        s.path(pts, color, w)

    # 1) accumulator
    y1, ph1 = 220, 110
    frame(y1, ph1, 'Phase accumulator acc (one voice, f = 2.5 kHz)', [(0, '0'), (0.5, '2²³'), (1, '2²⁴')])
    Y1 = lambda a: y1 + ph1 - a / 2 ** 24 * ph1
    stairs([a for _, a, _ in v1], Y1, C_PLUCK)
    for k, a, _ in v1:
        s.o.append(f'<circle cx="{X(k):.1f}" cy="{Y1(a):.1f}" r="3" fill="{C_PLUCK}" stroke="{SURF}" stroke-width="1.5"/>')
    s.text(x0 + pw / 2, y1 + ph1 + 18, f'each sample: acc += inc = {inc1:,}; past 2²⁴ it wraps and the next period starts'.replace(',', ' '), 11, INK2, 'middle')
    wrap_k = next(k for k in range(1, n) if v1[k][1] < v1[k - 1][1])

    # 2) output of the voice
    y2, ph2 = 400, 110
    frame(y2, ph2, 'Sample = wavetable[acc >> 16]  (sine table, 0…63)', [(0, '0'), (0.5, '32'), (1, '63')])
    Y2 = lambda v: y2 + ph2 - v / 63 * ph2
    ideal = [(X(t / 10), Y2((math.sin(2 * math.pi * 2500 * (t / 10) / fs) + 1) * 31.5)) for t in range(0, n * 10 + 1)]
    s.path(ideal, '#c9c8c2', 1.2, '3 3')
    stairs([table[i] for _, _, i in v1], Y2, C_PLUCK)
    s.text(x0 + pw + 8, Y2(57), 'held for one', 11, INK2); s.text(x0 + pw + 8, Y2(57) + 14, 'sample (32 µs)', 11, INK2)
    s.text(x0 + pw + 8, Y2(22), 'dashed: ideal', 11, INK2); s.text(x0 + pw + 8, Y2(22) + 14, 'sine', 11, INK2)

    # 3) sum of two voices
    y3, ph3 = 580, 130
    frame(y3, ph3, 'Two voices (2.5 kHz + 3.75 kHz) summed into OCR2B (0…255)', [(0, '0'), (0.5, '128'), (1, '255')])
    Y3 = lambda v: y3 + ph3 - v / 255 * ph3
    a = [table[i] for _, _, i in v1]; b = [table[i] for _, _, i in v2]
    stairs(a, Y3, C_PLUCK, 1.5); stairs(b, Y3, C_PAD, 1.5)
    stairs([p + q for p, q in zip(a, b)], Y3, C_AQUA, 2.4)
    labs = sorted([(Y3(a[-1] + b[-1]), 'sum → OCR2B', 600), (Y3(a[-1]), 'voice 1', 400), (Y3(b[-1]), 'voice 2', 400)])
    last = -1e9
    for yy, t, wgt in labs:      # keep end labels 14 px apart
        yy = max(yy, last + 14); last = yy
        s.text(x0 + pw + 8, yy + 4, t, 11.5, INK, weight=wgt)
    s.text(x0 + pw + 8, y3 + 14, 'other voices idle', 11, INK2)
    s.text(x0 + pw + 8, y3 + 28, '(N = 4 → each 0…63)', 11, INK2)
    s.text(x0 + pw / 2, y3 + ph3 + 22, f'samples (1 sample = 32 µs; {n} samples ≈ {n*32/1000:.1f} ms)', 11, INK2, 'middle')
    for k in range(0, n + 1, 4):
        s.line(X(k), y3 + ph3, X(k), y3 + ph3 + 4, AXIS)

    # legend
    lx, ly = 92, H - 12
    for i, (col, name) in enumerate(((C_PLUCK, 'voice 1'), (C_PAD, 'voice 2'), (C_AQUA, 'sum (PWM duty)'))):
        xx = lx + i * 150
        s.path([(xx, ly - 4), (xx + 28, ly - 4)], col, 2)
        s.text(xx + 36, ly, name, 11.5, INK)

    # side note: why it is exact and cheap
    nx = 700
    notes = ['Why DDS:', '• pitch = inc, not a timer:', '  24-bit step → < 0.05 cent', '• every voice shares one', '  timer and one table',
             '• cost per voice: add +', '  lookup ≈ 30 cycles', '  (sine + env ≈ 36)', '• no division in the ISR']
    for i, t in enumerate(notes):
        s.text(nx, 236 + i * 18, t, 11.5 if i else 12, INK if i == 0 else INK2, weight=600 if i == 0 else 400)
    s.save(fn, 'How a poly voice makes sound: DDS',
           'Block chain from note to OCR2B, then aligned plots of the phase accumulator, the looked-up samples and the sum of two voices.')

dds(sys.argv[1] + '/dds.svg')
shapes(sys.argv[1] + '/env-shapes.svg')
times(sys.argv[1] + '/env-times.svg')
