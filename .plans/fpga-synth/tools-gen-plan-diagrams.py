#!/usr/bin/env python3
"""Структурные схемы стендов для plan.md -> .plans/fpga-synth/img/plan_*.svg (+ png через chromium/cairosvg).

    python3 .plans/fpga-synth/tools-gen-plan-diagrams.py
"""
import os
import html

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'img')
KIND = {  # заливка, обводка
    'fpga': ('#ece0f8', '#6a3fa0'), 'mod': ('#d9f2d9', '#2e7d32'), 'bread': ('#fde2c8', '#b5651d'),
    'inst': ('#e3e8ef', '#475569'), 'pc': ('#d8e7fa', '#1f5fa8'), 'avk': ('#fff3b0', '#9a7d00'),
    'board': ('#fbe4ec', '#a33a63'), 'note': ('#ffffff', '#999999'),
}
LEGEND = [('fpga', 'ПЛИС / Tang Nano 20K'), ('mod', 'готовый модуль'), ('bread', 'макетка (своя схема)'),
          ('board', 'несущая плата блока'), ('inst', 'прибор'), ('pc', 'ПК'), ('avk', 'АВК-6')]


class Diagram:
    def __init__(self, name, w, h, title):
        self.name, self.w, self.h, self.title = name, w, h, title
        self.el, self.boxes = [], {}

    def box(self, bid, x, y, w, h, kind, title, lines=()):
        f, s = KIND[kind]
        self.boxes[bid] = (x, y, w, h)
        dash = ' stroke-dasharray="6 4"' if kind == 'note' else ''
        self.el.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{f}" stroke="{s}" stroke-width="1.6"{dash}/>')
        n = 1 + len(lines)
        y0 = y + h / 2 - (n - 1) * 8 + 4.5
        self.txt(x + w / 2, y0, title, 13.5, 'middle', bold=True)
        for i, ln in enumerate(lines):
            self.txt(x + w / 2, y0 + 16 * (i + 1), ln, 11.5, 'middle', '#333')

    def group(self, x, y, w, h, title, color='#999'):
        self.el.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="none" stroke="{color}" '
                       f'stroke-width="1.4" stroke-dasharray="7 5"/>')
        self.txt(x + 10, y + 17, title, 12.5, color=color, bold=True)

    def txt(self, x, y, t, size=12, anchor='start', color='#222', bold=False):
        b = ' font-weight="bold"' if bold else ''
        self.el.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" fill="{color}"{b}>'
                       f'{html.escape(t)}</text>')

    def p(self, bid, side, frac=0.5):
        x, y, w, h = self.boxes[bid]
        return {'l': (x, y + h * frac), 'r': (x + w, y + h * frac),
                't': (x + w * frac, y), 'b': (x + w * frac, y + h)}[side]

    def wire(self, pts, label=None, lpos=0, color='#333', both=False, dash=False, lx=None, ly=None, anchor='middle'):
        d = ' '.join(f'{x},{y}' for x, y in pts)
        ms = ' marker-start="url(#ah)"' if both else ''
        da = ' stroke-dasharray="5 3"' if dash else ''
        self.el.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="1.6"{da}{ms} marker-end="url(#ah)"/>')
        if label:
            (x1, y1), (x2, y2) = pts[lpos], pts[lpos + 1]
            self.txt(lx if lx is not None else (x1 + x2) / 2, ly if ly is not None else (y1 + y2) / 2 - 5,
                     label, 11, anchor, '#444')

    def mark(self, x, y, label):
        """Точка проверки: красная метка с номером пункта таблицы."""
        w = 9 + 7.2 * len(label)
        self.el.append(f'<rect x="{x - w / 2}" y="{y - 10}" width="{w}" height="18" rx="9" fill="#c62828"/>')
        self.txt(x, y + 3.5, label, 11, 'middle', '#fff', bold=True)

    def save(self, legend=True):
        body = list(self.el)
        if legend:
            lx, ly = 20, self.h - 22
            body.append(f'<text x="{lx}" y="{ly + 12}" font-size="11.5" fill="#555">Обозначения:</text>')
            x = lx + 90
            for k, t in LEGEND:
                f, s = KIND[k]
                body.append(f'<rect x="{x}" y="{ly}" width="18" height="14" rx="3" fill="{f}" stroke="{s}"/>')
                body.append(f'<text x="{x + 24}" y="{ly + 11.5}" font-size="11.5" fill="#333">{t}</text>')
                x += 34 + 7 * len(t)
            body.append(f'<rect x="{x}" y="{ly}" width="34" height="14" rx="7" fill="#c62828"/>'
                        f'<text x="{x + 17}" y="{ly + 11}" font-size="10" text-anchor="middle" fill="#fff" '
                        f'font-weight="bold">А2.1</text>'
                        f'<text x="{x + 42}" y="{ly + 11.5}" font-size="11.5" fill="#333">точка проверки (пункт таблицы)</text>')
        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" '
               f'height="{self.h}" font-family="DejaVu Sans, Arial, sans-serif">',
               '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
               'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#333"/></marker></defs>',
               f'<rect width="{self.w}" height="{self.h}" fill="#fff"/>',
               f'<text x="20" y="30" font-size="17" font-weight="bold" fill="#222">{html.escape(self.title)}</text>']
        svg += body + ['</svg>']
        os.makedirs(OUT, exist_ok=True)
        path = os.path.join(OUT, f'plan_{self.name}.svg')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(svg))
        return path


# ---------------------------------------------------------------- общий вид стенда (часть А)
def stand():
    D = Diagram('stand', 1500, 860, 'Стенд на отладочных платах (часть А): общий вид')
    D.box('pc', 20, 70, 220, 150, 'pc', 'ПК', ['Gowin EDA, openFPGALoader', 'load.py — прошивка CPU', 'консоль UART 1 Мбод',
                                                'hil.py — сценарии + анализ'])
    D.box('sc', 20, 250, 220, 80, 'inst', 'Звуковая карта', ['вход по пост. току', '(или осциллограф с записью)'])
    D.box('umidi', 20, 360, 220, 70, 'inst', 'USB-MIDI интерфейс', ['стимулы hil.py'])
    D.box('kbd', 20, 450, 220, 60, 'inst', 'MIDI-клавиатура', [])
    D.group(270, 55, 520, 640, 'Цифровая часть (3.3 В от Tang Nano / 3V3 стенда)', '#6a3fa0')
    D.box('tn', 410, 250, 240, 230, 'fpga', 'Tang Nano 20K', ['synth_core / stub_core / mono_core', 'встроенная SDRAM 64 Мбит',
                                                           'слот SD-карты', 'BL702: JTAG + UART', 'выводы — таблица Ж0.1'])
    D.box('dac', 290, 80, 200, 80, 'mod', 'PCM5102A', ['модуль (GY-PCM5102)', 'I2S, XSMT'])
    D.box('fl', 560, 80, 200, 80, 'mod', 'SPI-флеш W25Q64', ['модуль', 'прошивка + калибровки'])
    D.box('midi', 290, 560, 220, 110, 'bread', 'MIDI-вход', ['TRS-гнездо', 'мост 2×BAT54S + H11L1'])
    D.box('pan', 540, 520, 230, 160, 'bread', 'Панель', ['MCP3208 + 8 потенциометров', '4 × EC11 (подтяжки, RC)',
                                                      'ST7789 1.14″ (модуль)'])
    D.group(820, 55, 420, 640, 'Аналоговая часть (лаб. источник ±15 В, 3V3A)', '#b5651d')
    D.box('ain', 850, 90, 360, 120, 'bread', 'Входные каскады ВХ1, ВХ2', ['сумматор-сдвиг 100k/20k/24.9k', 'ФНЧ Саллена–Ки 20 кГц, OPA2350',
                                                                       'REF3025 2.5 В'])
    D.box('adc', 850, 240, 360, 70, 'bread', '2 × AD7091R', ['на переходниках MSOP-10 → DIP'])
    D.box('aout', 850, 340, 360, 120, 'bread', 'Выходные каскады', ['OPA2171 ×4.24 → ВЫХ, ВЫХ2', 'ГРОМКОСТЬ 10к',
                                                                 'LM339: индикаторы ±10 В'])
    D.box('sync', 850, 490, 360, 80, 'bread', 'Вход СИНХР', ['22k + BAT54S + 74LVC1G17'])
    D.box('psu', 850, 600, 360, 70, 'inst', 'Лабораторный источник', ['+5 В, ±15 В, ограничение тока'])
    D.box('gen', 1270, 90, 210, 90, 'inst', 'Генератор / АВК-6', ['±10 В, 0.1 Гц…20 кГц', 'ТТЛ для СИНХР'])
    D.box('osc', 1270, 230, 210, 90, 'inst', 'Осциллограф', ['2–4 канала, БПФ'])
    D.box('dmm', 1270, 350, 210, 70, 'inst', 'Мультиметр', ['4½ разряда'])
    D.box('load', 1270, 450, 210, 70, 'inst', 'Нагрузка', ['2 кОм ‖ 1 нФ на ВЫХ'])
    D.wire([D.p('pc', 'r', 0.85), (440, 197.5), (440, 250)], 'USB: JTAG + UART', 0, both=True, lx=330, ly=192)
    D.wire([D.p('tn', 't', 0.25), (470, 160)], 'I2S', 0, lx=500, ly=215)
    D.wire([D.p('tn', 't', 0.75), (590, 160)], 'SPI', 0, lx=615, ly=215, both=True)
    D.wire([D.p('midi', 't', 0.6), (420, 480)], 'midi_rx', 0, lx=380, ly=530)
    D.wire([D.p('pan', 't', 0.3), (610, 480)], 'SPI ×2, 12 линий', 0, lx=660, ly=505, both=True)
    D.wire([D.p('adc', 'l'), (720, 275), (720, 330), (650, 330)], 'SPI, CONVST', 0, lx=760, ly=268)
    D.wire([(490, 150), (525, 150), (525, 185), (780, 185), (780, 390), D.p('aout', 'l')], 'DAC_L, DAC_R', 2, lx=700, ly=180)
    D.wire([D.p('sync', 'l'), (700, 530), (700, 450), (650, 450)], 'sync_in', 0, lx=750, ly=525)
    D.wire([D.p('ain', 'b'), D.p('adc', 't')])
    D.wire([D.p('gen', 'l'), D.p('ain', 'r', 0.4)], 'ВХ1, ВХ2', 0)
    D.wire([(1270, 165), (1240, 165), (1240, 530), D.p('sync', 'r')], 'СИНХР', 1, lx=1236, ly=588, anchor='end')
    D.wire([D.p('aout', 'r', 0.5), (1250, 400), (1250, 485), D.p('load', 'l')])
    D.wire([D.p('kbd', 'r'), (265, 480), (265, 615), D.p('midi', 'l')])
    D.wire([D.p('umidi', 'r'), (255, 395), (255, 600), (290, 600)], dash=True)
    D.wire([D.p('aout', 'r', 0.25), (1255, 370), (1255, 275), D.p('osc', 'l')], dash=True)
    D.wire([(290, 140), (255, 140), (255, 290), D.p('sc', 'r')], 'линейный выход модуля', 0, lx=200, ly=245, dash=True)
    D.wire([D.p('psu', 'l'), (835, 635), (835, 150), (850, 150)], dash=True)
    D.txt(20, 740, 'Сплошные стрелки — сигналы; пунктир — питание, измерения и стимулы. Своя схема на макетке — те же номиналы, что в hw/schematic.md;', 12, color='#444')
    D.txt(20, 758, 'на переходниках — микросхемы без DIP-корпуса (AD7091R, OPA2171). Земли стенда, источника и приборов — в одной точке.', 12, color='#444')
    return D.save()


# ---------------------------------------------------------------- А2: цифровое ядро
def a2():
    D = Diagram('a2', 1300, 560, 'А2. Цифровое ядро: ПЛИС, ЦАП, флеш, SDRAM, SD')
    D.box('pc', 20, 120, 230, 130, 'pc', 'ПК', ['openFPGALoader → битстрим', 'load.py → прошивка CPU', 'консоль: memtest, sdtest, tone, dc'])
    D.box('tn', 380, 90, 300, 300, 'fpga', 'Tang Nano 20K', ['stub_core → synth_core', '', 'SDRAM 2M × 32 (внутри)', 'слот SD (на плате)',
                                                           'светодиоды 0–5: GPIO, MIDI, trap'])
    D.box('fl', 380, 430, 300, 70, 'mod', 'SPI-флеш W25Q64 (модуль)', ['flash_* — выводы 73, 74, 75, 85'])
    D.box('dac', 810, 90, 230, 110, 'mod', 'PCM5102A (модуль)', ['FMT=0, FLT=1, SCK=GND', 'XSMT ← dac_xsmt'])
    D.box('osc', 1080, 60, 200, 80, 'inst', 'Осциллограф', ['частота, форма, BCK/LRCK'])
    D.box('dmm', 1080, 170, 200, 70, 'inst', 'Мультиметр', ['DC на выходе ЦАП'])
    D.box('hp', 1080, 270, 200, 70, 'inst', 'Наушники', ['или звуковая карта'])
    D.box('sd', 810, 300, 230, 90, 'mod', 'SD-карты', ['SDHC 4–32 ГБ ×3, SDSC ≤ 2 ГБ', 'FAT16 / FAT32'])
    D.wire([D.p('pc', 'r', 0.4), D.p('tn', 'l', 0.2)], 'USB: JTAG + UART', 0, both=True)
    D.wire([D.p('tn', 'r', 0.2), D.p('dac', 'l', 0.4)], 'BCK, LRCK, DIN, XSMT', 0)
    D.wire([D.p('tn', 'b', 0.5), D.p('fl', 't', 0.5)], both=True)
    D.wire([D.p('tn', 'r', 0.8), D.p('sd', 'l', 0.5)], 'слот на плате', 0, both=True)
    D.wire([D.p('dac', 'r', 0.3), (1060, 123), (1060, 100), D.p('osc', 'l')])
    D.wire([D.p('dac', 'r', 0.6), (1060, 156), (1060, 205), D.p('dmm', 'l')])
    D.wire([D.p('dac', 'r', 0.9), (1050, 189), (1050, 305), D.p('hp', 'l')])
    D.mark(315, 192, 'А2.1')
    D.mark(530, 340, 'А2.4')
    D.mark(745, 162, 'А2.2')
    D.mark(1180, 160, 'А2.3')
    D.mark(560, 415, 'А2.5')
    D.mark(745, 315, 'А2.6')
    D.mark(1180, 255, 'А2.7')
    return D.save()


# ---------------------------------------------------------------- А3: MIDI и панель
def a3():
    D = Diagram('a3', 1300, 600, 'А3. Управление: MIDI-вход и панель')
    D.box('kbd', 20, 80, 200, 70, 'inst', 'MIDI-клавиатура', ['DIN-5'])
    D.box('cab', 20, 180, 200, 80, 'inst', 'Переходники DIN → TRS', ['Type A и Type B'])
    D.box('midi', 270, 100, 260, 140, 'bread', 'MIDI-вход (макетка)', ['TRS-гнездо', 'R301 220, мост 2×BAT54S', 'H11L1 + 2.2 кОм к 3V3'])
    D.box('tn', 600, 100, 260, 300, 'fpga', 'Tang Nano 20K', ['synth_core + прошивка', 'консоль: panel, screen,', 'lcdtest, stat'])
    D.box('dac', 930, 100, 200, 70, 'mod', 'PCM5102A', [])
    D.box('osc', 1160, 80, 130, 120, 'inst', 'Осциллограф', ['CH1: H11L1', 'CH2: ЦАП'])
    D.box('pots', 270, 290, 260, 110, 'bread', 'MCP3208 + 8 × B10K', ['RC 1 кОм / 100 нФ', 'VREF = 3V3A стенда'])
    D.box('enc', 270, 430, 260, 100, 'bread', '4 × EC11', ['подтяжки 10 кОм', 'RC 10 кОм / 10 нФ'])
    D.box('lcd', 600, 450, 260, 80, 'mod', 'ST7789 1.14″ (модуль)', ['SPI + DC, RST, BL'])
    D.wire([D.p('kbd', 'b'), D.p('cab', 't')])
    D.wire([D.p('cab', 'r'), (245, 220), (245, 170), D.p('midi', 'l')])
    D.wire([D.p('midi', 'r'), (600, 170)], 'midi_rx', 0)
    D.wire([D.p('tn', 'r', 0.23), D.p('dac', 'l')], 'I2S', 0)
    D.wire([D.p('dac', 'r', 0.4), D.p('osc', 'l', 0.55)])
    D.wire([(565, 170), (565, 60), (1145, 60), (1145, 165), (1160, 165)], dash=True)
    D.txt(620, 54, 'CH1 — выход оптрона, CH2 — выход ЦАП: задержка MIDI → звук', 11, color='#444')
    D.wire([D.p('pots', 'r'), (600, 345)], 'SPI (pot_*)', 0, both=True)
    D.wire([D.p('enc', 'r'), (570, 480), (570, 385), (600, 385)], 'enc_a/b/sw ×4', 1, lx=560, ly=440, anchor='end')
    D.wire([D.p('tn', 'b', 0.5), D.p('lcd', 't', 0.5)], 'SPI (lcd_*)', 0, lx=780, ly=430)
    D.mark(245, 105, 'А3.1')
    D.mark(565, 85, 'А3.2')
    D.mark(1225, 225, 'А3.3')
    D.mark(400, 415, 'А3.4')
    D.mark(400, 545, 'А3.5')
    D.mark(730, 545, 'А3.6')
    return D.save()


# ---------------------------------------------------------------- А4: аналоговые каскады
def a4():
    D = Diagram('a4', 1500, 700, 'А4. Аналоговые каскады на макетке: входы, АЦП, СИНХР, выходы, индикаторы')
    D.box('psu', 20, 70, 230, 90, 'inst', 'Лаб. источник', ['±15 В (огранич. 50 мА) → ОУ, LM339', '+5 В → LP5907 → 3V3A, REF'])
    D.box('gen', 20, 200, 230, 100, 'inst', 'Генератор / прецизионный', ['источник ±10 В', 'синус 1 кГц, меандр'])
    D.box('ttl', 20, 340, 230, 70, 'inst', 'ТТЛ / ±10 В меандр', ['0.1 Гц … 1.1 кГц'])
    D.box('ain', 300, 190, 300, 130, 'bread', 'Входной каскад ×2', ['сумматор-сдвиг 0.1·Vin + 1.25 В', 'D401 BAT54S', 'Саллен–Ки 20 кГц, OPA2350'])
    D.box('ref', 300, 70, 300, 80, 'bread', 'REF3025 → REF2V5', ['опора смещения и АЦП'])
    D.box('adc', 650, 190, 230, 130, 'bread', '2 × AD7091R', ['общие CONVST, CS, SCLK', 'раздельные SDO', 'REFIN ← REF2V5 (HO-09)'])
    D.box('sync', 300, 340, 300, 70, 'bread', 'СИНХР', ['22k, BAT54S, 470k, 74LVC1G17'])
    D.box('tn', 930, 190, 220, 220, 'fpga', 'Tang Nano 20K', ['synth_core', 'avk, cal, dc, stat'])
    D.box('dac', 930, 470, 220, 70, 'mod', 'PCM5102A', ['выход DC (HO-03)'])
    D.box('aout', 500, 450, 330, 140, 'bread', 'Выходные каскады (±15 В)', ['ГРОМКОСТЬ 10к → OPA2171 ×4.24 → ВЫХ', 'DAC_R → OPA2171 ×4.24 → ВЫХ2',
                                                                         'R704/R708 100 Ом в петле ОС'])
    D.box('led', 120, 450, 300, 100, 'bread', 'Индикаторы ±10 В', ['LM339 от ±15 В', 'детектор + растяжка 66 мс'])
    D.box('meas', 1220, 190, 260, 170, 'inst', 'Осциллограф + мультиметр', ['DC: смещение, масштаб', 'шум, THD (БПФ)',
                                                                          'разбег каналов', 'устойчивость'])
    D.box('ld', 1220, 470, 260, 80, 'inst', 'Нагрузка', ['2 кОм ‖ 1 нФ, КЗ на землю'])
    D.wire([D.p('gen', 'r', 0.5), D.p('ain', 'l', 0.5)], 'ВХ1, ВХ2', 0)
    D.wire([D.p('ref', 'b'), D.p('ain', 't')])
    D.wire([D.p('ref', 'r'), (765, 110), D.p('adc', 't')], 'REF2V5', 0, lx=700, ly=103)
    D.wire([D.p('ain', 'r'), D.p('adc', 'l')], 'AIN1, AIN2', 0)
    D.wire([D.p('adc', 'r', 0.5), (930, 255)], 'SPI', 0, both=True)
    D.wire([D.p('ttl', 'r'), D.p('sync', 'l')], 'СИНХР', 0)
    D.wire([D.p('sync', 'r'), (900, 375), (930, 375)], 'sync_in', 0, lx=760, ly=368)
    D.wire([D.p('tn', 'b'), D.p('dac', 't')], 'I2S', 0, lx=1065, ly=450)
    D.wire([D.p('dac', 'l'), (830, 505)], 'DAC_L, DAC_R', 0, lx=880, ly=498)
    D.wire([D.p('aout', 'l', 0.5), D.p('led', 'r', 0.7)], 'ВЫХ', 0, lx=460, ly=513)
    D.wire([(830, 560), (1190, 560), (1190, 510), D.p('ld', 'l')], 'ВЫХ, ВЫХ2', 0, lx=1000, ly=553)
    D.wire([D.p('tn', 'r', 0.35), D.p('meas', 'l', 0.4)], 'консоль', 0, dash=True)
    D.mark(455, 335, 'А4.1')
    D.mark(765, 335, 'А4.2')
    D.mark(275, 270, 'А4.3')
    D.mark(450, 425, 'А4.4')
    D.mark(890, 480, 'А4.5')
    D.mark(665, 610, 'А4.6')
    D.mark(270, 570, 'А4.7')
    D.mark(1350, 575, 'А4.8')
    return D.save()


# ---------------------------------------------------------------- А5: стенд целиком + АВК проводами
def a5():
    D = Diagram('a5', 1400, 600, 'А5. Стенд целиком: сравнение с симуляцией и первая работа с АВК-6 проводами')
    D.box('pc', 20, 80, 260, 150, 'pc', 'ПК: hil.py', ['стимулы MIDI из fpga/sim/system', 'запись ВЫХ/ВЫХ2', 'те же анализаторы и допуски',
                                                     'отчёт: железо vs симуляция'])
    D.box('umidi', 20, 270, 260, 70, 'inst', 'USB-MIDI', [])
    D.box('sc', 20, 380, 260, 80, 'inst', 'Звуковая карта (DC)', ['2 канала, 48/96 кГц'])
    D.box('stand', 380, 120, 360, 300, 'fpga', 'Стенд А2–А4', ['Tang Nano 20K + модули + макетки', '', 'ВХ1, ВХ2, СИНХР ← АВК',
                                                             'ВЫХ, ВЫХ2 → АВК / звуковая карта', 'MIDI ← USB-MIDI / клавиатура',
                                                             'консоль: stat (переполнения)'])
    D.box('avk', 960, 80, 420, 360, 'avk', 'АВК-6', ['генератор: синус, меандр 0.1…1100 Гц', 'выход меандра (СИНХР) — с разъёма',
                                                    'интегратор, умножитель, сумматоры', 'индикатор XY', '',
                                                    'соединение проводами со штырями стенда,', 'общая земля — одна точка'])
    D.wire([D.p('pc', 'b'), D.p('umidi', 't')])
    D.wire([D.p('umidi', 'r'), (330, 305), (330, 360), (380, 360)], 'MIDI', 0)
    D.wire([(380, 400), (310, 400), (310, 420), D.p('sc', 'r')], 'ВЫХ, ВЫХ2', 0, lx=340, ly=392)
    D.wire([D.p('pc', 'r', 0.5), (380, 155)], 'USB: консоль', 0, both=True)
    D.wire([D.p('avk', 'l', 0.2), (740, 152)], 'генератор → ВХ1', 0)
    D.wire([D.p('avk', 'l', 0.35), (740, 206)], 'меандр → СИНХР', 0)
    D.wire([(740, 290), D.p('avk', 'l', 0.58)], 'ВЫХ2: ENV / LFO / 1 В/окт', 0)
    D.wire([(740, 350), D.p('avk', 'l', 0.75)], 'ВЫХ → сумматор, XY', 0)
    D.mark(330, 250, 'А5.1')
    D.mark(560, 450, 'А5.2')
    D.mark(850, 120, 'А5.3')
    D.mark(850, 380, 'А5.4')
    D.mark(1170, 470, 'А5.5')
    return D.save()


# ---------------------------------------------------------------- Б3: первое включение платы
def b3():
    D = Diagram('b3', 1500, 640, 'Б3. Первое включение несущей платы: порядок и контрольные точки')
    steps = [
        ('1. Голая плата', ['омметр: шины на землю', '+5, ±15, 3V3x, REF — не КЗ', 'ориентация полярных']),
        ('2. Питание', ['лаб. источник через', 'кабель нижнего разъёма', 'ток ≤ 50 мА на шину', 'TP101…TP107']),
        ('3. Аналог без ПЛИС', ['REF2V5, 3V3A — шум', 'ВЫХ/ВЫХ2 ≈ 0 В', 'входы: 0 В → AIN = 1.25 В', 'индикаторы гаснут']),
        ('4. Tang Nano', ['stub_core: синус', 'консоль, флеш', 'ток +5 В в норме']),
        ('5. Все узлы', ['повтор А2–А4', 'на плате', 'cal, cal save']),
        ('6. Панель', ['дисплей за окном', 'ручки, энкодеры', 'гнёзда, светодиоды']),
    ]
    x = 20
    for i, (t, ls) in enumerate(steps):
        D.box(f's{i}', x, 80, 220, 140, 'board', t, ls)
        if i:
            D.wire([D.p(f's{i - 1}', 'r'), D.p(f's{i}', 'l')])
        D.mark(x + 110, 240, f'Б3.{i + 1}')
        x += 245
    D.group(20, 280, 1460, 300, 'Плата и где мерить', '#a33a63')
    D.box('pwr', 40, 320, 280, 230, 'board', 'Лист power', ['J101 нижний разъём', 'FB101–103, C101–C106', 'D102 → 5V_TN', 'U101 3V3A  U102 3V3D',
                                                             'U103 3V3H  U104 REF2V5', 'TP101…TP109'])
    D.box('dig', 360, 320, 260, 230, 'fpga', 'Tang Nano + флеш', ['гнёзда J201/J202', 'U201 W25Q64', 'TP201…TP207: I2S,', 'adc_sclk, sdo1,', 'midi_rx, sync_in'])
    D.box('ana', 660, 320, 280, 230, 'board', 'analog_in', ['входные каскады', 'AD7091R ×2', 'TP401, TP451: AIN1/2'])
    D.box('out', 980, 320, 260, 230, 'board', 'audio_out + phones', ['PCM5102A: TP601/602', 'OPA2171: TP701/702', 'LM339, LED701/702',
                                                                   'TPA6132A2: TP801'])
    D.box('pnl', 1270, 320, 190, 230, 'board', 'panel', ['MCP3208', 'EC11 ×4', 'J901 дисплей', 'J911…J914 штыри'])
    return D.save()


# ---------------------------------------------------------------- Б4: блок на столе через проставку
def b4():
    D = Diagram('b4', 1400, 560, 'Б4. Готовый блок на столе: проставка вместо корзины АВК')
    D.box('psu', 20, 90, 240, 100, 'inst', 'Лаб. источник', ['+5 В, ±15 В', 'ток и пульсации — как у АВК'])
    D.box('gen', 20, 230, 240, 100, 'inst', 'Генератор', ['ВХ1, ВХ2, СИНХР'])
    D.box('pc', 20, 370, 240, 110, 'pc', 'ПК', ['USB-C Tang Nano: консоль', 'hil.py, USB-MIDI'])
    D.box('adp', 330, 90, 250, 120, 'avk', 'Проставка (ремонтный модуль)', ['ответный нижний разъём', 'блок выше корпуса:', 'доступ к USB-C и SD'])
    D.box('blk', 650, 90, 380, 380, 'board', 'Готовый блок', ['несущая плата + Tang Nano 20K', 'панель 120 × 90 мм', '',
                                                           'штыри 2РМТ: ВХ1, ВХ2, ВЫХ, ВЫХ2', 'MIDI TRS, НАУШН./ЛИН.',
                                                           'ручки, энкодеры, дисплей, LED ±10', '', 'контрольные точки TPxxx'])
    D.box('meas', 1100, 90, 280, 150, 'inst', 'Осциллограф + мультиметр', ['шум выходов и входов', 'наводки SDRAM / дисплея', 'пороги индикаторов'])
    D.box('ph', 1100, 280, 280, 80, 'inst', 'Наушники 32 / 250 Ом', ['и линейный вход'])
    D.box('sc', 1100, 390, 280, 80, 'inst', 'Звуковая карта', ['ВЫХ, ВЫХ2, НАУШН./ЛИН.'])
    D.wire([D.p('psu', 'r'), D.p('adp', 'l', 0.33)])
    D.wire([D.p('adp', 'r', 0.5), D.p('blk', 'l', 0.13)], 'нижний разъём', 0)
    D.wire([D.p('gen', 'r'), (620, 280), (650, 280)], 'на штыри', 0)
    D.wire([D.p('pc', 'r'), (620, 425), (650, 425)], 'USB-C, MIDI', 0)
    D.wire([D.p('blk', 'r', 0.2), D.p('meas', 'l', 0.6)])
    D.wire([D.p('blk', 'r', 0.55), D.p('ph', 'l')])
    D.wire([D.p('blk', 'r', 0.85), D.p('sc', 'l', 0.6)])
    D.mark(450, 235, 'Б4.1')
    D.mark(840, 490, 'Б4.2')
    D.mark(1240, 260, 'Б4.3')
    D.mark(1240, 380, 'Б4.4')
    D.mark(1240, 490, 'Б4.5')
    return D.save()


# ---------------------------------------------------------------- Б5: блок в АВК
def b5():
    D = Diagram('b5', 1400, 600, 'Б5. Блок в корзине АВК-6: интеграция и демонстрационные наборы')
    D.box('avk', 20, 70, 1360, 430, 'avk', '', [])
    D.txt(40, 95, 'АВК-6: сборочная панель на 6 сменных модулей, генератор, индикатор XY, источник питания', 13, bold=True)
    D.box('gen', 60, 130, 230, 120, 'avk', 'Генератор АВК', ['синус / меандр', '0.1 … 1100 Гц', 'меандр → нижний разъём'])
    D.box('blk', 380, 130, 300, 300, 'board', 'Блок синтезатора', ['слот сборочной панели', 'питание и СИНХР — нижний разъём', '',
                                                                 'ВХ1, ВХ2 ← модули АВК', 'ВЫХ, ВЫХ2 → модули АВК', 'MIDI ← клавиатура',
                                                                 'НАУШН./ЛИН. → запись'])
    D.box('int', 770, 130, 260, 90, 'avk', 'Линейный блок', ['интегратор'])
    D.box('mul', 770, 240, 260, 90, 'avk', 'Умножитель / нелинейный', [])
    D.box('xy', 1080, 130, 270, 120, 'avk', 'Индикатор XY', ['фазовые траектории', 'осциллограммы'])
    D.box('sum', 770, 350, 260, 80, 'avk', 'Сумматоры', [])
    D.wire([D.p('gen', 'r', 0.3), D.p('blk', 'l', 0.13)], 'ВХ1 (срез, высота)', 0)
    D.wire([D.p('gen', 'b'), (175, 290), D.p('blk', 'l', 0.53)], 'СИНХР (ноты, такт)', 1, lx=270, ly=283)
    D.wire([D.p('blk', 'r', 0.2), D.p('int', 'l', 0.5)], 'ВЫХ2: ENV', 0)
    D.wire([D.p('blk', 'r', 0.5), D.p('mul', 'l', 0.5)], 'ВЫХ', 0)
    D.wire([D.p('mul', 'r', 0.5), (1055, 285), (1055, 210), (1080, 210)])
    D.wire([D.p('int', 'r', 0.5), D.p('xy', 'l', 0.3)])
    D.wire([D.p('sum', 'l', 0.5), D.p('blk', 'r', 0.85)], '→ ВХ2', 0)
    D.mark(530, 450, 'Б5.1')
    D.mark(310, 205, 'Б5.2')
    D.mark(725, 155, 'Б5.3')
    D.mark(1215, 270, 'Б5.4')
    D.txt(20, 535, 'Наборы (пункт Б5.3): синт под управлением АВК (ВХ → срез, СИНХР → ноты, жёсткая синхронизация); АВК под управлением синта', 12, color='#444')
    D.txt(20, 553, '(ВЫХ2 = огибающая, LFO, 1 В/окт → интегратор, умножитель); обработка сигналов АВК (MATH как умножитель, DELAY, REVERB на ВХ).', 12, color='#444')
    return D.save()


if __name__ == '__main__':
    for f in (stand, a2, a3, a4, a5, b3, b4, b5):
        print(f())
