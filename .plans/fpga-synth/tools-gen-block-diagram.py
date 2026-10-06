# Генератор структурной схемы аппаратного блока (SVG)
W, H = 1640, 870
out = []
C = {  # домены
 'con': ('#e9e9e9', '#555'), 'a15': ('#fde2c8', '#b5651d'), 'a33': ('#d9f2d9', '#2e7d32'),
 'd33': ('#d8e7fa', '#1f5fa8'), 'fpga': ('#ece0f8', '#6a3fa0'), 'pwr': ('#fff3b0', '#9a7d00'),
}
def box(x, y, w, h, dom, lines, bold=False, fs=13):
    f, s = C[dom]
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{f}" stroke="{s}" stroke-width="1.4"/>')
    n = len(lines); lh = fs + 3
    y0 = y + h/2 - (n-1)*lh/2 + fs*0.35
    for i, t in enumerate(lines):
        wgt = ' font-weight="bold"' if (bold and i == 0) else ''
        out.append(f'<text x="{x+w/2}" y="{y0+i*lh}" font-size="{fs if i==0 else fs-1.5}" text-anchor="middle"{wgt}>{t}</text>')
def arrow(pts, label=None, lx=None, ly=None, color='#333', dash=False, both=False):
    d = ' '.join(f'{x},{y}' for x, y in pts)
    da = ' stroke-dasharray="5 3"' if dash else ''
    ms = ' marker-start="url(#ah)"' if both else ''
    out.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="1.5"{da}{ms} marker-end="url(#ah)"/>')
    if label:
        x = lx if lx is not None else (pts[0][0]+pts[1][0])/2
        y = ly if ly is not None else pts[0][1]-5
        out.append(f'<text x="{x}" y="{y}" font-size="11" text-anchor="middle" fill="#444">{label}</text>')
def text(x, y, t, fs=12, anchor='start', color='#222', bold=False):
    b = ' font-weight="bold"' if bold else ''
    out.append(f'<text x="{x}" y="{y}" font-size="{fs}" text-anchor="{anchor}" fill="{color}"{b}>{t}</text>')


# ---------- колонки ----------
XC, WC = 20, 105          # разъёмы входа
X1, W1 = 150, 175
X2, W2 = 345, 165
XA, WA = 530, 100         # АЦП
XF, WF = 655, 300         # ПЛИС
XD, WD = 1060, 120         # ЦАП
XV, WV = 1205, 120        # громкость
XO, WO = 1355, 145        # ОУ
XR, WR = 1520, 105        # разъёмы выхода

# ---------- питание ----------
text(20, 22, 'ПОДСИСТЕМА ПИТАНИЯ', 14, bold=True)
box(20, 34, 140, 96, 'con', ['Нижний разъём', 'модуля АВК', '+5 · +15 · −15', '⊥ · СИНХР'], True)
box(190, 34, 160, 96, 'pwr', ['Входные фильтры', 'ферр. бусина', '100 мкФ + 100 нФ', 'на каждой шине'], True)
box(380, 34, 160, 44, 'pwr', ['Шоттки SS14', '+5 → 5 В Tang Nano'], True, 12)
box(380, 86, 160, 44, 'a15', ['±15 В', 'ОУ выходов, LM339'], True, 12)
box(570, 34, 160, 44, 'a33', ['LDO 3.3A (LP5907)', 'ЦАП, АЦП, ОУ входов'], True, 12)
box(570, 86, 160, 44, 'd33', ['LDO 3.3D (AP2112)', 'логика, дисплей'], True, 12)
box(760, 34, 170, 44, 'a33', ['REF 2.5 В (REF3025)', 'опора АЦП + смещение'], True, 12)
box(760, 86, 170, 44, 'pwr', ['LDO 3.3H (300 мА)', 'усилитель наушников'], True, 12)
arrow([(160, 82), (190, 82)])
for yy in (56, 108):
    arrow([(350, 82), (365, 82), (365, yy), (380, yy)])
arrow([(540, 56), (555, 56), (555, 108), (570, 108)]); arrow([(555, 56), (570, 56)])
arrow([(555, 108), (555, 140), (745, 140), (745, 108), (760, 108)])
arrow([(730, 56), (760, 56)])

lx, ly = 1060, 30
text(lx, ly, 'Домены питания:', 12, bold=True)
for i, (k, t) in enumerate([('a15', 'аналог ±15 В'), ('a33', 'аналог 3.3A / REF'), ('d33', 'цифра 3.3D'), ('fpga', 'ПЛИС / Tang Nano'), ('pwr', 'питание'), ('con', 'разъёмы / панель')]):
    cx = lx + (i % 3) * 190; cy = ly + 14 + (i // 3) * 26
    f, s_ = C[k]
    out.append(f'<rect x="{cx}" y="{cy}" width="22" height="16" rx="3" fill="{f}" stroke="{s_}"/>')
    text(cx + 28, cy + 12.5, t, 12)
text(lx, ly + 80, 'ВХ, ВЫХ, ВЫХ2 — по постоянному току; FS = ±12.5 В, МЕ = ±10 В', 11, color='#555')
out.append(f'<line x1="10" y1="152" x2="{W-10}" y2="152" stroke="#bbb" stroke-dasharray="6 4"/>')

# ---------- ПЛИС ----------
FY, FH = 175, 640
box(XF, FY, WF, FH, 'fpga', [''])
text(XF + WF/2, FY + 22, 'Tang Nano 20K (GW2AR-18)', 15, 'middle', bold=True)
text(XF + WF/2, FY + 38, 'макет: Tang Nano 9K', 11, 'middle', '#555')
inner = [
 (FY+50,  ['MIDI UART 31250 + парсер', '→ FIFO событий']),
 (FY+100, ['Измеритель периода / фронт', 'СИНХР → такт, триггер нот']),
 (FY+150, ['SPI АЦП входов, 192 кSPS', '→ децимация → ВХ1, ВХ2']),
 (FY+200, ['PicoRV32 + BSRAM', 'распределение голосов, меню']),
 (FY+250, ['SPI MCP3208, декодеры', 'энкодеров, SPI дисплея']),
 (FY+300, ['Голосовой движок ×NUM_VOICES', 'NCO·2 → SVF → ×ADSR']),
 (FY+350, ['Шина сигналов + слоты FX', 'MATH, DELAY, CHORUS, REVERB']),
 (FY+400, ['Выходной микшер + лимитер', '→ I2S TX (L = ВЫХ, R = ВЫХ2)']),
]
for yy, ls in inner:
    out.append(f'<rect x="{XF+15}" y="{yy}" width="{WF-30}" height="42" rx="4" fill="#fff" stroke="#6a3fa0" stroke-width="0.8"/>')
    text(XF + WF/2, yy + 17, ls[0], 12, 'middle'); text(XF + WF/2, yy + 33, ls[1], 11, 'middle', '#555')
yy = FY + 470
text(XF + 15, yy, 'На плате Tang Nano:', 12, bold=True)
for i, t in enumerate(['SDRAM 64 Мбит (кольцевые буферы)', 'SPI-флеш (битстрим + прошивка CPU)', 'SD-карта (пресеты)', 'USB-C / BL702 (JTAG + UART-отладка)', 'кварц 27 МГц → PLL']):
    out.append(f'<rect x="{XF+15}" y="{yy+8+i*30}" width="{WF-30}" height="24" rx="3" fill="#f6f0fc" stroke="#9b7fc4" stroke-width="0.7"/>')
    text(XF + WF/2, yy + 25 + i*30, t, 11.5, 'middle')
text(XF + WF/2, FY + FH + 18, 'питание 5 В через гребёнку (после Шоттки)', 11, 'middle', '#555')

# ---------- входы ----------
text(20, 172, 'ВХОДЫ И ОРГАНЫ УПРАВЛЕНИЯ', 14, bold=True)
fx = XF
def row3(y, h, c, b1, b2, d1, d2, lab):
    box(XC, y, WC, h, 'con', c, True, 12)
    box(X1, y, W1, h, d1, b1, True, 12)
    if b2: box(X2, y, W2, h, d2, b2, True, 12)
    arrow([(XC+WC, y+h/2), (X1, y+h/2)])
    if b2:
        arrow([(X1+W1, y+h/2), (X2, y+h/2)])
        arrow([(X2+W2, y+h/2), (fx, y+h/2)], lab, lx=(XA+fx)/2 if lab else None, ly=y+h/2-5)
    else:
        arrow([(X1+W1, y+h/2), (fx, y+h/2)], lab, lx=(XA+fx)/2, ly=y+h/2-5)
row3(200, 46, ['MIDI', 'TRS 3.5 мм (A)'], ['Мост 2×BAT54S', 'для Type A и B'], ['Оптрон H11L1', 'подтяжка к 3.3D'], 'd33', 'd33', 'RX')
row3(262, 46, ['СИНХР', 'нижний разъём'], ['22 кОм + BAT54S', '+100 пФ, терпит ±15 В'], ['74LVC1G17', 'Шмитт, порог ~1.4 В'], 'd33', 'd33', 'SYNC')
for i, nm in enumerate(['ВХ1', 'ВХ2']):
    y = 330 + i*72
    box(XC, y, WC, 56, 'con', [nm, '±12.5 В FS', 'Rвх ≈ 111 кОм'], True, 12)
    box(X1, y, W1, 56, 'a33', ['Сумматор-сдвиг', '100k / 20k / 24.9k', '0.1·Vin+1.25 В, BAT54S'], True, 12)
    box(X2, y, W2, 56, 'a33', ['ФНЧ 20 кГц, 2 пор.', 'Саллен–Ки, ОУ RRIO', 'OPA2350, от 3.3A'], True, 12)
    box(XA, y, WA, 56, 'a33', ['АЦП', 'AD7091R', '12 бит 1 MSPS'], True, 12)
    arrow([(XC+WC, y+28), (X1, y+28)]); arrow([(X1+W1, y+28), (X2, y+28)]); arrow([(X2+W2, y+28), (XA, y+28)])
    arrow([(XA+WA, y+28), (fx, y+28)], 'SPI', ly=y+23)
text(XA + WA/2, 323, 'общий CONVST', 10.5, 'middle', '#555')
y = 476
box(X1, y, W1, 40, 'a33', ['REF 2.5 В', 'смещение + REFIN АЦП'], True, 12)
arrow([(X1+W1/2, y), (X1+W1/2, 402+56)], color='#2e7d32', dash=True)
arrow([(X1+W1/2, 402), (X1+W1/2, 386)], color='#2e7d32', dash=True)
arrow([(X1+W1, y+20), (XA+WA/2, y+20), (XA+WA/2, 402+56)], color='#2e7d32', dash=True)
row3(540, 56, ['8 потенциом.', 'B10K 9 мм'], ['RC 1 кОм + 100 нФ', 'питание = VREF', 'ратиометрично'], ['MCP3208', '8 кан., 12 бит', '≥100 Гц/канал'], 'a33', 'a33', 'SPI')
row3(610, 56, ['4 энкодера', 'EC11 + кнопка'], ['Подтяжки 10 кОм', 'RC 10k / 10 нФ', 'A, B, SW × 4'], None, 'd33', 'd33', '12 линий')
# дисплей
y = 682
box(XC, y, WC, 80, 'con', ['Дисплей', '1.14" ST7789', '240×135', 'за окном'], True, 12)
arrow([(fx, y+14), (XC+WC, y+14)], 'SPI: SCK, MOSI, CS, DC, RST', lx=(XC+WC+fx)/2, ly=y+9)
box(X2, y+30, W2, 50, 'd33', ['Подсветка', 'N-MOSFET AO3400'], True, 12)
arrow([(fx, y+55), (X2+W2, y+55)], 'BL (ШИМ)', lx=(X2+W2+fx)/2, ly=y+50)
arrow([(X2, y+55), (XC+WC, y+55)])

# ---------- выходы ----------
text(XD, 172, 'ВЫХОДЫ', 14, bold=True)
box(XD, 215, WD, 330, 'a33', ['PCM5102A', 'I2S ЦАП', 'стерео, 32 бит', 'FLT = low latency', 'выход DC', '±2.97 В пик = FS', '', 'L → ВЫХ, НАУШН.', 'R → ВЫХ2'], True, 13)
arrow([(XF+WF, FY+415), (XD-22, FY+415), (XD-22, 440), (XD, 440)])
text(XF+WF+5, FY+409, 'I2S: BCK, LRCK, DIN', 10, color='#444')
arrow([(XF+WF, FY+432), (XD-10, FY+432), (XD-10, 525), (XD, 525)], dash=True)
text(XF+WF+5, FY+446, 'XSMT', 10, color='#444')
y = 230
box(XV, y, WV, 54, 'con', ['ГРОМКОСТЬ', '10 кОм, на панели', 'max = ×1'], True, 12)
box(XO, y, WO, 54, 'a15', ['ОУ ×4.24', 'OPA2171 (A), ±15 В', 'ФНЧ 49 кГц'], True, 12)
box(XR, y, WR, 54, 'con', ['ВЫХ', 'штырь 2РМТ', '±12.5 В DC'], True, 12)
arrow([(XD+WD, y+27), (XV, y+27)], 'L', ly=y+22); arrow([(XV+WV, y+27), (XO, y+27)]); arrow([(XO+WO, y+27), (XR, y+27)])
y = 310
box(XO, y, WO, 54, 'a15', ['LM339', 'пороги ±10 В', 'растяжка ≥ 50 мс'], True, 12)
box(XR, y, WR, 54, 'con', ['LED', '+10 / −10', 'на панели'], True, 12)
arrow([(XO+WO+10, 257), (XO+WO+10, 297), (XO+WO/2, 297), (XO+WO/2, y)])
arrow([(XO+WO, y+27), (XR, y+27)])
y = 390
box(XO, y, WO, 54, 'a33', ['Усил. наушников', 'TPA6132A2, 3.3H', 'вход: 1 мкФ, ×0.5'], True, 12)
box(XR, y, WR, 54, 'con', ['НАУШН./ЛИН.', 'TRS 3.5 мм', '16–600 Ом'], True, 12)
arrow([(XV+WV/2, 284), (XV+WV/2, y+27), (XO, y+27)])
text(XV+WV/2-6, y+18, 'движок', 10.5, 'end', '#444'); text(XV+WV/2-6, y+31, 'громкости', 10.5, 'end', '#444')
arrow([(XO+WO, y+27), (XR, y+27)])
y = 475
box(XO, y, WO, 54, 'a15', ['ОУ ×4.24', 'OPA2171 (B)', 'без регулятора'], True, 12)
box(XR, y, WR, 54, 'con', ['ВЫХ2', 'штырь 2РМТ', '±12.5 В DC'], True, 12)
arrow([(XD+WD, y+27), (XO, y+27)], 'R', ly=y+22); arrow([(XO+WO, y+27), (XR, y+27)])

text(XD+60, 600, 'ВЫХ2 — модуляция АВК от синта:', 12, bold=True)
for i, t in enumerate(['LFO1/2, огибающая, gate, pitch CV, velocity,', 'выход любого слота шины сигналов.', '',
                       'НАУШН./ЛИН. — готовый звук: наушники 16–600 Ом', 'или линейный вход; после громкости,', 'развязан по постоянному току, моно на T и R,', 'защита от КЗ (моно-штекер TS).']):
    text(XD+60, 620 + i*17, t, 11.5, color='#444')

svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="DejaVu Sans, Arial, sans-serif">',
       '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#333"/></marker></defs>',
       f'<rect width="{W}" height="{H}" fill="#fff"/>',
       f'<text x="{W/2}" y="{H-14}" font-size="12" text-anchor="middle" fill="#777">Структурная схема аппаратного блока FPGA-синтезатора АВК-6 · требования к узлам: hw-requirements.md</text>']
svg += out + ['</svg>']
open('/home/user/midi2aux/.plans/fpga-synth/block-diagram.svg', 'w').write('\n'.join(svg))
