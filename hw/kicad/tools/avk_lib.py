"""Собственные символы проекта (библиотека avk_synth): нет в стандартных библиотеках KiCad 7."""
from sexp import Sym

S = Sym


def _pin(etype, num, name, x, y, ang, length=2.54):
    return [S('pin'), S(etype), S('line'), [S('at'), x, y, ang], [S('length'), length],
            [S('name'), name, [S('effects'), [S('font'), [S('size'), 1.27, 1.27]]]],
            [S('number'), str(num), [S('effects'), [S('font'), [S('size'), 1.27, 1.27]]]]]


def _prop(name, val, y, hide=False):
    eff = [S('effects'), [S('font'), [S('size'), 1.27, 1.27]]]
    if hide:
        eff.append(S('hide'))
    return [S('property'), name, val, [S('at'), 0, y, 0], eff]


def _box(name, w, h, left, right, top, bot, ref, value, fp='', ds='', desc='', hide_numbers=False):
    """Прямоугольный символ: стороны — списки (etype, num, name)."""
    pins = []
    for i, (t, n, nm) in enumerate(left):
        pins.append(_pin(t, n, nm, -w / 2 - 2.54, h / 2 - 2.54 * (i + 1), 0))
    for i, (t, n, nm) in enumerate(right):
        pins.append(_pin(t, n, nm, w / 2 + 2.54, h / 2 - 2.54 * (i + 1), 180))
    for i, (t, n, nm) in enumerate(top):
        pins.append(_pin(t, n, nm, -2.54 * (len(top) - 1) / 2 + 2.54 * i, h / 2 + 2.54, 270))
    for i, (t, n, nm) in enumerate(bot):
        pins.append(_pin(t, n, nm, -2.54 * (len(bot) - 1) / 2 + 2.54 * i, -h / 2 - 2.54, 90))
    rect = [S('rectangle'), [S('start'), -w / 2, h / 2], [S('end'), w / 2, -h / 2],
            [S('stroke'), [S('width'), 0.254], [S('type'), S('default')]], [S('fill'), [S('type'), S('background')]]]
    head = [S('symbol'), name] + ([[S('pin_numbers'), S('hide')]] if hide_numbers else [])
    return head + [[S('in_bom'), S('yes')], [S('on_board'), S('yes')],
                   _prop('Reference', ref, h / 2 + 1.5), _prop('Value', value, -h / 2 - 1.5),
                   _prop('Footprint', fp, 0, True), _prop('Datasheet', ds, 0, True),
                   _prop('ki_description', desc, 0, True),
                   [S('symbol'), name + '_0_1', rect],
                   [S('symbol'), name + '_1_1'] + pins]


def symbols():
    ad = _box('AD7091R', 15.24, 12.7,
              left=[('input', 3, 'VIN'), ('passive', 2, 'REFIN/REFOUT'), ('passive', 4, 'REGCAP')],
              right=[('input', 6, 'CONVST'), ('input', 7, '~{CS}'), ('input', 9, 'SCLK'), ('output', 8, 'SDO')],
              top=[('power_in', 1, 'VDD'), ('power_in', 10, 'VDRIVE')],
              bot=[('power_in', 5, 'GND')],
              ref='U', value='AD7091R', fp='Package_SO:MSOP-10_3x3mm_P0.5mm',
              ds='https://www.analog.com/media/en/technical-documentation/data-sheets/AD7091R.pdf',
              desc='12-bit 1 MSPS SAR ADC, SPI. НОМЕРА ВЫВОДОВ НЕ ПРОВЕРЕНЫ — сверить с даташитом (HO-09)')
    tn_left = [('output', '25', 'i2s_bck'), ('output', '26', 'i2s_lrck'), ('output', '27', 'i2s_din'),
               ('output', '28', 'dac_xsmt'), ('input', '29', 'midi_rx'), ('input', 'P_SYNC', 'sync_in'),
               ('output', 'P_CNV', 'adc_convst_n'), ('output', 'P_ACS', 'adc_cs_n'), ('output', 'P_ASCK', 'adc_sclk'),
               ('input', 'P_SDO1', 'adc_sdo1'), ('input', 'P_SDO2', 'adc_sdo2'),
               ('output', '73', 'flash_sck'), ('output', '74', 'flash_mosi'), ('input', '75', 'flash_miso'),
               ('output', '85', 'flash_cs_n')]
    tn_right = [('output', 'P_PSCK', 'pot_sck'), ('output', 'P_PMOSI', 'pot_mosi'), ('input', 'P_PMISO', 'pot_miso'),
                ('output', 'P_PCS', 'pot_cs_n'),
                ('output', 'P_LSCK', 'lcd_sck'), ('output', 'P_LMOSI', 'lcd_mosi'), ('output', 'P_LCS', 'lcd_cs_n'),
                ('output', 'P_LDC', 'lcd_dc'), ('output', 'P_LRST', 'lcd_rst_n'), ('output', 'P_LBL', 'lcd_bl')]
    tn_right += [('input', f'P_EA{i}', f'enc_a{i}') for i in range(4)]
    tn_right += [('input', f'P_EB{i}', f'enc_b{i}') for i in range(4)]
    tn_right += [('input', f'P_ES{i}', f'enc_sw{i}') for i in range(4)]
    tn_left = [(t, n, f'{nm} [IO{n}]' if n.isdigit() else nm) for t, n, nm in tn_left]
    tn = _box('Tang_Nano_20K', 35.56, 2.54 * (max(len(tn_left), len(tn_right)) + 1), tn_left, tn_right,
              [('power_in', '5V', '5V')], [('power_in', 'GND1', 'GND'), ('power_in', 'GND2', 'GND')], hide_numbers=True,
              ref='A', value='Tang Nano 20K', fp='',
              ds='https://wiki.sipeed.com/hardware/en/tang/tang-nano-20k/nano-20k.html',
              desc='Модуль Sipeed Tang Nano 20K на гребёнках. Номер вывода = номер IO ПЛИС из .cst (25…29, 73–75, 85); '
                   'P_* — ещё не назначены (HO-01). Посадочное место — после HO-01.')
    return {'AD7091R': ad, 'Tang_Nano_20K': tn}


def library_text():
    from sexp import dump
    lib = [S('kicad_symbol_lib'), [S('version'), 20220914], [S('generator'), S('avk_synth_gen')]]
    lib += list(symbols().values())
    return dump(lib) + '\n'
