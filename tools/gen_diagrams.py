#!/usr/bin/env python3
"""Block diagrams img/arch-mono.svg and img/arch-poly.svg.

usage: python3 tools/gen_diagrams.py img
"""
import sys
from xml.sax.saxutils import escape
W, H = 990, 520
COLX = [20, 220, 420, 620, 820]
ROWY = [60, 180, 300, 420]
BW, BH = 150, 64
STY = {
    'hw':    ('#eef2f7', '#5b6b7f'),
    'isr':   ('#fdf0dc', '#c47f17'),
    'timer': ('#e3f2e6', '#3d8b4f'),
    'main':  ('#ebe6f7', '#6b55a8'),
}

class D:
    def __init__(self, title):
        self.o = []
        self.o.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
        self.o.append(f'<text x="20" y="34" font-size="16" font-weight="600" fill="#1f2328">{escape(title)}</text>')
    def box(self, c, r, kind, title, *sub):
        x, y = COLX[c], ROWY[r]
        f, s = STY[kind]
        self.o.append(f'<rect x="{x}" y="{y}" width="{BW}" height="{BH}" rx="7" fill="{f}" stroke="{s}" stroke-width="1.5"/>')
        n = 1 + len(sub)
        ty = y + BH / 2 - (n - 1) * 7 + 4
        self.o.append(f'<text x="{x+BW/2}" y="{ty}" text-anchor="middle" font-size="12.5" font-weight="600" fill="#1f2328">{escape(title)}</text>')
        for i, t in enumerate(sub):
            self.o.append(f'<text x="{x+BW/2}" y="{ty+14*(i+1)}" text-anchor="middle" font-size="11" fill="#57606a">{escape(t)}</text>')
    def arrow(self, pts, label=None, lx=None, ly=None, anchor='middle'):
        d = 'M' + ' L'.join(f'{x},{y}' for x, y in pts)
        self.o.append(f'<path d="{d}" fill="none" stroke="#444c56" stroke-width="1.4" marker-end="url(#a)"/>')
        if label:
            self.o.append(f'<text x="{lx}" y="{ly}" text-anchor="{anchor}" font-size="10.5" font-style="italic" fill="#444c56">{escape(label)}</text>')
    def legend(self):
        x, y = COLX[2], ROWY[3] + 18
        for i, (k, name) in enumerate([('hw', 'hardware / pins'), ('isr', 'interrupt handler'),
                                       ('timer', 'timer peripheral'), ('main', 'main loop / data')]):
            f, s = STY[k]
            xx = x + (i % 2) * 190
            yy = y + (i // 2) * 26
            self.o.append(f'<rect x="{xx}" y="{yy}" width="16" height="14" rx="3" fill="{f}" stroke="{s}" stroke-width="1.5"/>')
            self.o.append(f'<text x="{xx+24}" y="{yy+11}" font-size="11.5" fill="#1f2328">{name}</text>')
    def svg(self):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
                f'font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif">\n'
                '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
                'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#444c56"/></marker></defs>\n'
                + '\n'.join(self.o) + '\n</svg>\n')

def L(c): return COLX[c]
def R(c): return COLX[c] + BW
def CX(c): return COLX[c] + BW / 2
def T(r): return ROWY[r]
def B(r): return ROWY[r] + BH
def CY(r): return ROWY[r] + BH / 2

def common(d, timer2_sub, poly=False):
    d.box(0, 0, 'hw', 'MIDI IN', 'DIN-5, 31 250 baud')
    d.box(1, 0, 'hw', 'Optocoupler', 'RX gate: PD2')
    d.box(0, 1, 'hw', 'Potentiometer', 'PC0 / ADC0')
    d.box(1, 1, 'isr', 'ADC_vect ISR', 'free-running, 104 µs', 'ADCH → potValue')
    d.box(0, 2, 'hw', 'Button', 'PC1, pull-up')
    if poly:
        d.box(1, 2, 'isr', 'TIMER1_COMPA ISR', '1 ms envelope tick', 'button every 10 ms')
    else:
        d.box(1, 2, 'isr', 'TIMER1_COMPA ISR', '10 ms tick, debounce', 'waveMode++, noteOff()')
    d.box(1, 3, 'hw', 'LEDs', 'PD4–PD6: waveform', 'PD7: note playing')
    d.box(4, 2, 'timer', 'Timer2 Fast PWM', *timer2_sub)
    d.box(4, 1, 'hw', 'RC low-pass', 'PWM → analog')
    d.box(4, 0, 'hw', 'AUX OUT')
    d.arrow([(R(0), CY(0)), (L(1), CY(0))])
    d.arrow([(R(1), CY(0)), (L(2), CY(0))], 'PD0', (R(1) + L(2)) / 2, CY(0) - 7)
    d.arrow([(R(0), CY(1)), (L(1), CY(1))])
    d.arrow([(R(0), CY(2)), (L(1), CY(2))])
    d.arrow([(CX(1), B(2)), (CX(1), T(3))], 'mode LEDs', CX(1) + 6, B(2) + 32, 'start')
    d.arrow([(CX(4), T(2)), (CX(4), B(1))], 'OC2B / PD3', CX(4) + 6, B(1) + 32, 'start')
    d.arrow([(CX(4), T(1)), (CX(4), B(0))])
    d.arrow([(R(3), CY(2)), (L(4), CY(2))], 'OCR2B', (R(3) + L(4)) / 2, CY(2) - 7)
    d.legend()

# ---- mono
d = D('MIDI2AUX — mono mode (default build)')
common(d, ('160 kHz, TOP = 99', '100 levels'))
d.box(2, 0, 'isr', 'USART_RX ISR', 'UDR0 → midiParser()')
d.box(3, 0, 'isr', 'noteOn / noteOff', 'last note wins', 'period = table[note]')
d.box(3, 1, 'timer', 'Timer0 CTC', 'IRQ rate = note × 64', 'prescaler 8 / 64')
d.box(3, 2, 'isr', 'TIMER0_COMPA ISR', 'phase 0…63 → sample', 'square · triangle · sine')
d.arrow([(R(2), CY(0)), (L(3), CY(0))])
d.arrow([(CX(3), B(0)), (CX(3), T(1))], 'OCR0A, prescaler', CX(3) + 6, B(0) + 32, 'start')
d.arrow([(CX(3), B(1)), (CX(3), T(2))], 'compare match', CX(3) + 6, B(1) + 32, 'start')
d.arrow([(R(1), CY(1)), (CX(2), CY(1)), (CX(2), T(2) + 18), (L(3), T(2) + 18)],
        'potValue', R(1) + 8, CY(1) - 7, 'start')
d.arrow([(R(1), T(2) + 46), (L(3), T(2) + 46)], 'waveMode', CX(2), T(2) + 40)
open(sys.argv[1] + '/arch-mono.svg', 'w').write(d.svg())

# ---- poly
d = D('MIDI2AUX — poly mode (POLY_VOICES = N, default 4)')
common(d, ('62.5 kHz, TOP = 255', '256 levels'), poly=True)
d.box(2, 0, 'isr', 'USART_RX ISR', 'UDR0 → ring buffer [16]')
d.box(3, 0, 'main', 'main loop', 'uart_poll → midiParser', 'voice alloc / release')
d.box(3, 1, 'main', 'N voices (1…16)', 'acc += inc (24 bit)', 'sine: envelope level')
d.box(2, 1, 'main', 'wavetable[256]', 'rebuilt in main loop', 'on mode / pot change')
d.box(2, 2, 'timer', 'Timer0 CTC', 'fixed fs = 31.25 kHz', 'prescaler 8, OCR0A = 63')
d.box(3, 2, 'isr', 'TIMER0_COMPA ISR', 'OCR2B = previous sum', 'Σ table[acc>>16] · env')
d.arrow([(R(2), CY(0)), (L(3), CY(0))], 'bytes', (R(2) + L(3)) / 2, CY(0) - 7)
d.arrow([(CX(3), B(0)), (CX(3), T(1))], 'inc[v] = f(note)', CX(3) + 6, B(0) + 32, 'start')
d.arrow([(CX(3), B(1)), (CX(3), T(2))])
d.arrow([(R(1), CY(1) - 10), (L(2), CY(1) - 10)], 'potValue', (R(1) + L(2)) / 2, CY(1) - 17)
d.arrow([(R(1), T(2) + 18), ((R(1) + L(2)) / 2, T(2) + 18), ((R(1) + L(2)) / 2, CY(1) + 16), (L(2), CY(1) + 16)],
        'waveMode', (R(1) + L(2)) / 2 + 5, B(1) + 32, 'start')
d.arrow([(CX(2) + 40, B(1)), (CX(2) + 40, (B(1) + T(2)) / 2), (L(3) + 30, (B(1) + T(2)) / 2), (L(3) + 30, T(2))])
d.arrow([(R(2), CY(2)), (L(3), CY(2))], 'IRQ', (R(2) + L(3)) / 2, CY(2) - 7)
open(sys.argv[1] + '/arch-poly.svg', 'w').write(d.svg())
