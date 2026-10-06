#!/usr/bin/env python3
"""Схемы узлов для hw/schematic.md (schemdraw + matplotlib).

    pip install schemdraw matplotlib
    python3 hw/img/gen_schematics.py        -> hw/img/sch_*.svg, sch_*.png
"""
import os
import schemdraw
import schemdraw.elements as elm
import schemdraw.logic as logic

schemdraw.use('matplotlib')
schemdraw.config(font='DejaVu Sans', fontsize=11, unit=2.5, lw=1.4)
OUT = os.path.dirname(os.path.abspath(__file__))
NET = '#1f5fa8'   # имена цепей
NOTE = '#666'     # пояснения


def save(d, name):
    for ext in ('svg', 'png'):
        d.save(os.path.join(OUT, f'sch_{name}.{ext}'), dpi=150)


def net(d, text, loc='right', open_=True):
    """Открытая точка с именем цепи."""
    return d.add(elm.Dot(open=open_).label(text, loc=loc, color=NET))


def note(d, xy, text, fs=9):
    d.add(elm.Label().at(xy).label(text, color=NOTE, fontsize=fs, halign='left'))


def gnd(d):
    d.add(elm.Ground())


def cap_down(d, at, label, polar=False):
    d.push()
    d.add(elm.Capacitor(polar=polar).down().at(at).label(label, loc='bottom', fontsize=10))
    gnd(d)
    d.pop()


def ic(d, name, left=(), right=(), top=(), bot=(), w=3, label_loc='top'):
    pins = [elm.IcPin(name=n, pin=p, side='left') for n, p in left]
    pins += [elm.IcPin(name=n, pin=p, side='right') for n, p in right]
    pins += [elm.IcPin(name=n, pin=p, side='top') for n, p in top]
    pins += [elm.IcPin(name=n, pin=p, side='bottom') for n, p in bot]
    return elm.Ic(pins=pins, edgepadW=0.5, edgepadH=0.6, pinspacing=1.0, w=w,
                  leadlen=0.6).label(name, loc=label_loc, fontsize=11)


# ---------------------------------------------------------------- power
def power():
    with schemdraw.Drawing(show=False) as d:
        # +5
        net(d, '+5 (J101)', loc='left')
        d += elm.Inductor2(loops=2).right().label('FB101')
        n = d.add(elm.Dot())
        cap_down(d, n.center, 'C101\n100 мкФ', polar=True)
        d += elm.Line().right(2.6)
        n = d.add(elm.Dot())
        cap_down(d, n.center, 'C102\n100 нФ')
        d += elm.Line().right(2.6)
        p5 = d.add(elm.Dot().label('+5V_IN', loc='bottom', color=NET))
        # D102 -> 5V_TN
        d += elm.Line().up(4).at(p5.center)
        d += elm.Schottky().right().label('D102 SS14')
        net(d, '5V_TN → вывод 5 V гребёнки Tang Nano')
        # LDO stack
        d += elm.Line().right(2).at(p5.center)
        prev = d.here
        ldos = [('U101 LP5907-3.3', '3V3A', 'аналог: ЦАП, АЦП, ОУ, MCP3208, REF'),
                ('U102 AP2112K-3.3', '3V3D', 'цифра: VDRIVE, флеш, логика, дисплей'),
                ('U103 AP2112K-3.3', '3V3H', 'наушники')]
        for i, (name, rail, use) in enumerate(ldos):
            if i:
                d += elm.Line().down(4.4).at(prev)
                prev = d.here
            d += elm.Line().right(1).at(prev)
            u = d.add(ic(d, name, left=[('IN', '1'), ('EN', '3')], right=[('OUT', '5')],
                         bot=[('GND', '2')]).anchor('IN'))
            d += elm.Line().at(u.IN).to(u.EN)
            d += elm.Ground().at(u.GND)
            d += elm.Line().right(1.2).at(u.OUT)
            o = d.add(elm.Dot())
            cap_down(d, o.center, '1 мкФ' if rail == '3V3A' else '1 мкФ + 10 мкФ')
            d += elm.Line().right(1.5).at(o.center)
            net(d, f'{rail}  ({use})')
        note(d, (0.3, -6.3), 'Вход каждого LDO: 1 мкФ (C107, C109, C112).\nEN соединён с IN.')
        # REF от 3V3A
        y = prev[1] - 6
        d += elm.Dot(open=True).at((p5.center[0] + 0.5, y)).label('3V3A', loc='left', color=NET)
        d += elm.Resistor().right().label('R101 10')
        rn = d.add(elm.Dot())
        cap_down(d, rn.center, 'C115\n1 мкФ')
        d += elm.Line().right(1.5).at(rn.center)
        u = d.add(ic(d, 'U104 REF3025', left=[('IN', '1')], right=[('OUT', '2')], bot=[('GND', '3')]).anchor('IN'))
        d += elm.Ground().at(u.GND)
        d += elm.Line().right(1.2).at(u.OUT)
        o = d.add(elm.Dot())
        cap_down(d, o.center, 'C116\n1 мкФ')
        d += elm.Line().right(1.5).at(o.center)
        net(d, 'REF2V5  (REFIN АЦП, смещение входов, пороги LED)')

        # ±15
        for k, (lbl, fb, c, dname, neg) in enumerate([('+15 (J101)', 'FB102', 'C103\n47 мкФ', 'D103', False),
                                                     ('−15 (J101)', 'FB103', 'C105\n47 мкФ', 'D104', True)]):
            y = -22 - k * 6
            d += elm.Dot(open=True).at((0, y)).label(lbl, loc='left', color=NET)
            d += elm.Inductor2(loops=2).right().label(fb)
            n = d.add(elm.Dot())
            d.push()
            cap = elm.Capacitor(polar=True).down().label(c, loc='bottom', fontsize=10)
            d += (cap.reverse() if neg else cap)
            gnd(d)
            d.pop()
            d += elm.Line().right(2.6)
            n2 = d.add(elm.Dot())
            cap_down(d, n2.center, '100 нФ')
            d += elm.Line().right(2.6)
            n3 = d.add(elm.Dot())
            d.push()
            sd = elm.Schottky().down().label(f'{dname}\nSS14', loc='bottom', fontsize=10)
            d += (sd if neg else sd.reverse())
            gnd(d)
            d.pop()
            d += elm.Line().right(1.5).at(n3.center)
            net(d, '−15V → лист aout' if neg else '+15V → лист aout')
        d += elm.Dot(open=True).at((0, -33)).label('СИНХР (J101)', loc='left', color=NET)
        d += elm.Line().right(9)
        net(d, 'SYNC_RAW → лист midi_sync')
    save(d, 'power')


# ---------------------------------------------------------------- MIDI
def midi():
    with schemdraw.Drawing(show=False) as d:
        j = d.add(elm.AudioJack(ring=True).label('J301\nTRS 3.5 мм', loc='left'))
        cx, cy = j.tip[0] + 9, j.tip[1] - 2.2
        top, bot, lft, rgt = (cx, cy + 2.2), (cx, cy - 2.2), (cx - 2.2, cy), (cx + 2.2, cy)
        # T -> R301 -> AC1 (верх), R -> AC2 (низ)
        d += elm.Line().right(1).at(j.tip)
        d += elm.Resistor().right().label('R301 220')
        d += elm.Line().to((cx, j.tip[1]))
        d += elm.Line().to(top)
        d += elm.Line().at(j.ring).right(1)
        d += elm.Line().to((j.ring[0] + 1, bot[1]))
        d += elm.Line().to(bot)
        d += elm.Dot().at(top).label('AC1', loc='left', fontsize=9)
        d += elm.Dot().at(bot).label('AC2', loc='left', fontsize=9)
        # мост: аноды на AC → DC+, DC− → AC
        d += elm.Schottky().at(top).to(rgt).label('D301', fontsize=9)
        d += elm.Schottky().at(bot).to(rgt).label('D302', loc='bottom', fontsize=9)
        d += elm.Schottky().at(lft).to(top).label('D301', fontsize=9)
        d += elm.Schottky().at(lft).to(bot).label('D302', loc='bottom', fontsize=9)
        d += elm.Dot().at(rgt).label('DC+', loc='right', fontsize=9, ofst=(0.1, 0.35))
        d += elm.Dot().at(lft).label('DC−', loc='left', fontsize=9)
        note(d, (j.sleeve[0] - 4.2, j.sleeve[1] - 0.9), 'S — не подключать')
        # оптрон
        u = d.add(ic(d, '', left=[('K', '2'), ('A', '1')], right=[('Vo', '4')],
                     top=[('VCC', '6')], bot=[('GND', '5')], w=3.2).right()
                  .at((rgt[0] + 3, rgt[1])).anchor('A'))
        d.add(elm.Label().at((u.A[0] + 0.6, u.VCC[1] + 0.5)).label('U301 H11L1', halign='right', fontsize=11))
        d += elm.Line().at(rgt).to(u.A)
        yb = bot[1] - 1.2
        d += elm.Line().at(lft).to((lft[0], yb))
        d += elm.Line().to((rgt[0] + 1.8, yb))
        d += elm.Line().to((rgt[0] + 1.8, u.K[1]))
        d += elm.Line().to(u.K)
        d += elm.Line().at(u.VCC).up(0.6)
        d += elm.Vdd().label('3V3D')
        d += elm.Ground().at(u.GND)
        d += elm.Line().right(1.5).at(u.Vo)
        vo = d.add(elm.Dot())
        d.push()
        d += elm.Resistor().up().label('R302\n2.2к', loc='bottom')
        d += elm.Vdd().label('3V3D')
        d.pop()
        d += elm.Resistor().right().label('R303 33')
        net(d, 'midi_rx')
        note(d, (j.sleeve[0] - 0.2, bot[1] - 2.6),
             'D301, D302 — BAT54S (по 2 диода в корпусе): мост делает кабели Type A и Type B равноценными.\n'
             'Ток петли ≈ 5 мА, порог H11L1 ≤ 1.6 мА; Vo = 0, пока течёт ток (бит «0»), покой — 1.')
    save(d, 'midi')


# ---------------------------------------------------------------- SYNC
def sync():
    with schemdraw.Drawing(show=False) as d:
        net(d, 'SYNC_RAW (J101)', loc='left')
        d += elm.Resistor().right().label('R304\n22к')
        n = d.add(elm.Dot())
        for dx, lab in ((0, None),):
            pass
        # ограничитель BAT54S: к 3V3D и к GND
        d.push()
        d += elm.Schottky().up().label('D303\n(BAT54S)', loc='bottom', fontsize=9)
        d += elm.Vdd().label('3V3D')
        d.pop()
        d.push()
        d += elm.Schottky().down().reverse()
        gnd(d)
        d.pop()
        d += elm.Line().right(2).at(n.center)
        n2 = d.add(elm.Dot())
        cap_down(d, n2.center, 'C303\n100 пФ')
        d += elm.Line().right(2).at(n2.center)
        n3 = d.add(elm.Dot())
        d.push()
        d += elm.Resistor().down().label('R305\n470к', loc='bottom')
        gnd(d)
        d.pop()
        d += elm.Line().right(1.5).at(n3.center)
        d += elm.Dot().label('TP301', loc='top', fontsize=9, color=NOTE)
        g = d.add(logic.Schmitt().right().label('U302\n74LVC1G17', loc='top', ofst=0.6))
        d += elm.Dot().at(g.out).label('TP302', loc='bottom', fontsize=9, color=NOTE)
        d += elm.Resistor().right().at(g.out).label('R306\n33')
        net(d, 'sync_in')
        note(d, (n.center[0] - 7, n.center[1] - 4.6), 'U302: VCC = 3V3D, GND. Узел ограничен −0.3…3.6 В; ТТЛ «1» ≥ 2.4 В → ≥ 2.29 В на входе (> VT+).')
    save(d, 'sync')


# ---------------------------------------------------------------- AIN
def ain():
    with schemdraw.Drawing(show=False) as d:
        net(d, 'ВХ1 (штырь)', loc='left')
        d += elm.Resistor().right().label('R401 100к 0.1%')
        node = d.add(elm.Dot().label('узел', loc='bottom', fontsize=9, ofst=(0.45, -0.1)))
        d.push()
        d += elm.Resistor().up().label('R402\n20.0к 0.1%', loc='bottom')
        net(d, 'REF2V5', loc='top', open_=False)
        d.pop()
        d += elm.Line().right(1.8)
        n2 = d.add(elm.Dot())
        d.push()
        d += elm.Resistor().down().label('R403\n24.9к 0.1%', loc='bottom')
        gnd(d)
        d.pop()
        d += elm.Line().right(3.2)
        cl = d.add(elm.Dot())
        d.push()
        d += elm.Schottky().up().label('D401\nBAT54S', loc='bottom', fontsize=9)
        d += elm.Vdd().label('3V3A')
        d.pop()
        d.push()
        d += elm.Schottky().down().reverse()
        gnd(d)
        d.pop()
        d += elm.Line().right(1.8)
        c1 = d.add(elm.Dot())
        d += elm.Resistor().right().label('R404 10.0к')
        p = d.add(elm.Dot())
        cap_down(d, p.center, 'C402\n560 пФ')
        d += elm.Line().right(1).at(p.center)
        op = d.add(elm.Opamp(leads=True).anchor('in2').label('U401A\nOPA2350', loc='center', ofst=(-0.4, 0), fontsize=9))
        d += elm.Vdd().at(op.vd).label('3V3A')
        d += elm.Ground().at(op.vs)
        xo = op.out[0] + 0.8
        o = d.add(elm.Dot().at((xo, op.out[1])))
        d += elm.Line().at(op.out).to(o.center)
        # повторитель: IN− на выход
        yf = op.in1[1] + 1.4
        d += elm.Line().at(op.in1).left(0.4)
        d += elm.Line().to((op.in1[0] - 0.4, yf))
        d += elm.Line().to((xo, yf))
        d += elm.Line().to(o.center)
        # C401: от узла фильтра (c1) на выход ОУ
        yc = yf + 1.6
        d += elm.Line().at(c1.center).to((c1.center[0], yc))
        cap = d.add(elm.Capacitor().right().at((c1.center[0], yc)).label('C401 1.1 нФ'))
        d += elm.Line().at(cap.end).to((xo + 0.01, yc))
        d += elm.Line().to((xo + 0.01, yf))
        d += elm.Resistor().right().at(o.center).label('R405 49.9')
        a = d.add(elm.Dot())
        cap_down(d, a.center, 'C403\n2.2 нФ')
        d += elm.Line().right(1.2).at(a.center)
        net(d, 'AIN1 → VIN АЦП U501')
        note(d, (-1, -5.0),
             'Vузла = 0.1·Vin + 1.25 В (±12.5 В → 0…2.5 В).  R1 фильтра = R401‖R402‖R403 = 9.98 кОм (отдельный резистор не нужен).\n'
             'Саллен–Ки: R1 = 9.98 к, R2 = R404, C1 = C401, C2 = C402 → fc ≈ 20.3 кГц, Q ≈ 0.70.   ВХ2 — то же: позиции 45x, U401B.')
    save(d, 'ain')


# ---------------------------------------------------------------- AOUT
def aout():
    with schemdraw.Drawing(show=False) as d:
        net(d, 'DAC_L', loc='left')
        d += elm.Line().right(1)
        pot = d.add(elm.Potentiometer().down())
        d.add(elm.Label().at((pot.center[0] - 0.9, pot.center[1])).label('RV701\nГРОМКОСТЬ 10к\nверх — DAC_L', halign='right', fontsize=10))
        gnd(d)
        d += elm.Line().at(pot.tap).right(1.6)
        w = d.add(elm.Dot().label('VOL_W → лист hp', loc='bottom', color=NET, fontsize=10))
        d += elm.Resistor().right().at(w.center).label('R701 1к')
        d += elm.Line().right(0.6)
        op = d.add(elm.Opamp(leads=True).anchor('in2').label('U701A\nOPA2171', loc='center', ofst=(-0.4, 0), fontsize=9))
        d += elm.Vdd().at(op.vd).label('+15V')
        d += elm.Vss().at(op.vs).label('−15V')
        xo = op.out[0] + 0.6
        o = d.add(elm.Dot().at((xo, op.out[1])))
        d += elm.Line().at(op.out).to(o.center)
        d += elm.Resistor().right().at(o.center).label('R704 100')
        v = d.add(elm.Dot())
        d += elm.Line().right(1.2)
        net(d, 'ВЫХ (штырь)\n→ VOUT1_SENSE (индикаторы)')
        # узел IN−
        xm = op.in1[0] - 0.4
        ym = op.in1[1] + 2.6
        d += elm.Line().at(op.in1).to((xm, op.in1[1]))
        d += elm.Line().to((xm, ym))
        m = d.add(elm.Dot().at((xm, ym)))
        # Rg на землю (влево)
        d += elm.Resistor().left().at(m.center).label('R702 10.0к')
        d += elm.Line().down(0.8)
        d += elm.Ground()
        # Cf: выход ОУ -> IN−
        yc = ym + 0.01
        d += elm.Line().at(m.center).to((xm, ym + 1.6))
        cf = d.add(elm.Capacitor().right().at((xm, ym + 1.6)).label('C701 100 пФ'))
        d += elm.Line().at(cf.end).to((xo, ym + 1.6))
        d += elm.Line().to(o.center)
        # Rf: ВЫХ (после R704) -> IN−
        d += elm.Line().at((xm, ym + 1.6)).to((xm, ym + 3.4))
        rf = d.add(elm.Resistor().right().at((xm, ym + 3.4)).label('R703 32.4к'))
        d += elm.Line().at(rf.end).to((v.center[0], ym + 3.4))
        d += elm.Line().to(v.center)
        note(d, (-1, -5.2),
             'K = 1 + R703/R702 = 4.24 (±2.97 В ЦАП → ±12.6 В).  ОС снимается после R704 (100 Ом внутри петли — защита от КЗ и ёмкости кабеля);\n'
             'C701 — прямая ВЧ-связь с выхода ОУ: ФНЧ 49 кГц и устойчивость.  '
             'ВЫХ2 — то же на U701B без ГРОМКОСТИ: DAC_R → R705 1к → IN+; R706, R707, C702, R708.')
    save(d, 'aout')


# ---------------------------------------------------------------- LED
def led():
    with schemdraw.Drawing(show=False) as d:
        def chain(d, y, sense_r, low_r, low_to, title, cin, cout, sname, dname, rname, cname, ledname, lr, ledlbl,
                  minus_on_sense):
            d.add(elm.Dot(open=True).at((0, y)).label('VOUT1_SENSE', loc='left', color=NET))
            d += elm.Resistor().right().label(sense_r)
            n = d.add(elm.Dot())
            d.push()
            d += elm.Resistor().down().label(low_r, loc='bottom')
            if low_to == 'GND':
                gnd(d)
            else:
                d += elm.Dot(open=True).label(low_to, loc='bottom', color=NET)
            d.pop()
            d += elm.Line().right(3.2)
            c = d.add(elm.Opamp(leads=True).anchor('in1' if minus_on_sense else 'in2')
                      .label(cin, loc='center', ofst=(-0.4, 0), fontsize=9))
            other = c.in2 if minus_on_sense else c.in1
            d += elm.Line().at(other).left(1.0)
            if minus_on_sense:
                d += elm.Line().down(1.0)
                d += elm.Dot(open=True).label('REF_CMP (2.5 В)', loc='bottom', color=NET)
            else:
                d += elm.Line().down(0.4)
                d += elm.Ground()
            # детектор → диод → узел растяжки
            d += elm.Line().right(0.8).at(c.out)
            d += elm.Diode().left().reverse().right().label(dname, fontsize=9)
            s = d.add(elm.Dot().label(sname, loc='top', fontsize=9))
            d.push()
            d += elm.Resistor().up().label(rname + '\n100к', loc='bottom')
            d += elm.Vdd().label('+15V')
            d.pop()
            d.push()
            d += elm.Capacitor().down().label(cname + '\n1 мкФ', loc='bottom')
            gnd(d)
            d.pop()
            d += elm.Line().right(3.2).at(s.center)
            c2 = d.add(elm.Opamp(leads=True).anchor('in2').flip().label(cout, loc='center', ofst=(-0.4, 0), fontsize=9))
            d += elm.Line().at(c2.in1).left(1.0)
            d += elm.Line().down(0.6)
            d += elm.Ground()
            d += elm.Line().right(0.8).at(c2.out)
            d += elm.LED().right().reverse().label(ledname + ' ' + ledlbl, fontsize=10)
            d += elm.Resistor().right().label(lr)
            gnd(d)
            return c

        chain(d, 0, 'R711 200к', 'R712\n66.5к', 'GND', '+', 'U702A\nдетектор', 'U702D\nрастяжка',
              'S1', 'D711', 'R715', 'C711', 'LED701', 'R717 6.8к', '«+10»', True)
        chain(d, -9, 'R713 200к', 'R714\n49.9к', 'REF_CMP', '−', 'U702B\nдетектор', 'U702C\nрастяжка',
              'S2', 'D712', 'R716', 'C712', 'LED702', 'R718 6.8к', '«−10»', False)
        note(d, (-1, -13.2), 'U702 LM339: VCC = +15V, вывод GND = −15V; выходы — открытый коллектор к −15 В.  Порог «+»: Vout > +10.02 В '
            '(0.2495·Vout > 2.5 В); порог «−»: Vout < −10.02 В.\nСрабатывание разряжает C711/C712 через диод; светодиод горит, '
            'пока узел S < 0 В: ≈ 66 мс после пика.  REF_CMP = REF2V5 через R719 100 Ом, C715 1 мкФ.')
    save(d, 'led')


if __name__ == '__main__':
    for f in (power, midi, sync, ain, aout, led):
        f()
        print('ok', f.__name__)
