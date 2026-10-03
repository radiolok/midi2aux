#!/usr/bin/env python3
"""Генерация схемы KiCad 7 несущей платы FPGA-синтезатора АВК-6.

Источник правды по номиналам и связям — этот файл (он повторяет hw/schematic.md).
Стиль схемы: символы сгруппированы по узлам, выводы соединены метками цепей
(локальные — внутри листа, глобальные — между листами, GND — символ питания).

    python3 hw/kicad/tools/gen_kicad.py     -> hw/kicad/*.kicad_sch, avk_synth.kicad_sym, проект
"""
import os
import sys
import uuid as _uuid
from collections import defaultdict, OrderedDict

sys.path.insert(0, os.path.dirname(__file__))
from sexp import Sym as S, dump, get  # noqa: E402
import kilib  # noqa: E402
import avk_lib  # noqa: E402

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PROJECT = 'avk_synth'
CUSTOM_LIB = 'avk_synth'
_uid_ns = _uuid.UUID('6f1c6e2a-1b4e-4a7a-9a3c-2d8a0c5e1f00')


def uid(*key):
    """Детерминированные UUID — чтобы перегенерация не меняла файлы зря."""
    return str(_uuid.uuid5(_uid_ns, '/'.join(map(str, key))))


# ------------------------------------------------------------------ посадочные места
FP = {
    'R0603': 'Resistor_SMD:R_0603_1608Metric', 'R0805': 'Resistor_SMD:R_0805_2012Metric',
    'C0603': 'Capacitor_SMD:C_0603_1608Metric', 'C0805': 'Capacitor_SMD:C_0805_2012Metric',
    'CP63': 'Capacitor_SMD:CP_Elec_6.3x5.4', 'L0805': 'Inductor_SMD:L_0805_2012Metric',
    'SOT23': 'Package_TO_SOT_SMD:SOT-23', 'SOT235': 'Package_TO_SOT_SMD:SOT-23-5',
    'SO8': 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm', 'SO14': 'Package_SO:SOIC-14_3.9x8.7mm_P1.27mm',
    'SO16': 'Package_SO:SOIC-16_3.9x9.9mm_P1.27mm', 'TSSOP20': 'Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm',
    'WQFN16': 'Package_DFN_QFN:WQFN-16-1EP_3x3mm_P0.5mm_EP1.68x1.68mm',
    'SMA': 'Diode_SMD:D_SMA', 'SOD123': 'Diode_SMD:D_SOD-123', 'SOD323': 'Diode_SMD:D_SOD-323',
    'LED3': 'LED_THT:LED_D3.0mm', 'POT9': 'Potentiometer_THT:Potentiometer_Alps_RK09K_Single_Vertical',
    'EC11': 'Rotary_Encoder:RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm',
    'DIP6': 'Package_DIP:SMDIP-6_W9.53mm', 'TP': 'TestPoint:TestPoint_Pad_D1.5mm',
    'JACK': 'Connector_Audio:Jack_3.5mm_Lumberg_1503_03_Horizontal',
    'PS1x8': 'Connector_PinSocket_2.54mm:PinSocket_1x08_P2.54mm_Vertical',
    'WIRE': 'Connector_Wire:SolderWire-0.5sqmm_1x01_D0.9mm_OD2.1mm',
}


# ------------------------------------------------------------------ описание деталей
class Part:
    def __init__(self, ref, lib, value, fp, pins, dnp=False, note=None):
        self.ref, self.lib, self.value, self.fp = ref, lib, value, FP.get(fp, fp)
        self.pins = {str(k): v for k, v in pins.items()}
        self.dnp, self.note = dnp, note


def R(ref, val, a, b, fp='R0603', **kw):
    return Part(ref, 'Device:R', val, fp, {1: a, 2: b}, **kw)


def C(ref, val, a, b, fp='C0603', **kw):
    return Part(ref, 'Device:C', val, fp, {1: a, 2: b}, **kw)


def CP(ref, val, plus, minus):
    return Part(ref, 'Device:C_Polarized', val, 'CP63', {1: plus, 2: minus})


def D(ref, lib, val, k, a, fp):
    return Part(ref, lib, val, fp, {1: k, 2: a})


def TP(ref, net):
    return Part(ref, 'Connector:TestPoint', net if not net.startswith('/') else net[1:], 'TP', {1: net})


def BAT54S(ref, a, k, com):
    return Part(ref, 'Diode:BAT54S', 'BAT54S', 'SOT23', {1: a, 2: k, 3: com})


NC = '~NC'

# ------------------------------------------------------------------ листы
SHEETS = OrderedDict()


def sheet(name, title, groups, notes=()):
    SHEETS[name] = dict(title=title, groups=groups, notes=list(notes))


# --- power
sheet('power', 'Питание: нижний разъём, фильтры, LDO, опора 2.5 В', [
    ('Нижний разъём модуля АВК-6 (распиновка — HO-06)', [
        Part('J101', 'Connector_Generic:Conn_01x05', 'АВК-6 модуль', '',
             {1: '+5_RAW', 2: '+15_RAW', 3: '-15_RAW', 4: 'GND', 5: 'SYNC_RAW'}),
        Part('#FLG101', 'power:PWR_FLAG', 'PWR_FLAG', '', {1: 'GND'}),
    ]),
    ('+5 В', [
        Part('FB101', 'Device:FerriteBead', '600R@100MHz 2A', 'L0805', {1: '+5_RAW', 2: '+5V_IN'}),
        CP('C101', '100u 10V', '+5V_IN', 'GND'), C('C102', '100n', '+5V_IN', 'GND'),
        Part('#FLG102', 'power:PWR_FLAG', 'PWR_FLAG', '', {1: '+5V_IN'}),
        D('D102', 'Diode:SS14', 'SS14', '5V_TN', '+5V_IN', 'SMA'),
        Part('#FLG103', 'power:PWR_FLAG', 'PWR_FLAG', '', {1: '5V_TN'}),
    ]),
    ('±15 В', [
        Part('FB102', 'Device:FerriteBead', '600R@100MHz', 'L0805', {1: '+15_RAW', 2: '+15V'}),
        CP('C103', '47u 25V', '+15V', 'GND'), C('C104', '100n', '+15V', 'GND'),
        D('D103', 'Diode:SS14', 'SS14', '+15V', 'GND', 'SMA'),
        Part('#FLG104', 'power:PWR_FLAG', 'PWR_FLAG', '', {1: '+15V'}),
        Part('FB103', 'Device:FerriteBead', '600R@100MHz', 'L0805', {1: '-15_RAW', 2: '-15V'}),
        CP('C105', '47u 25V', 'GND', '-15V'), C('C106', '100n', '-15V', 'GND'),
        D('D104', 'Diode:SS14', 'SS14', 'GND', '-15V', 'SMA'),
        Part('#FLG105', 'power:PWR_FLAG', 'PWR_FLAG', '', {1: '-15V'}),
    ]),
    ('LDO: 3V3A (аналог), 3V3D (цифра), 3V3H (наушники)', [
        Part('U101', 'Regulator_Linear:LP5907MFX-3.3', 'LP5907MFX-3.3', 'SOT235',
             {1: '+5V_IN', 2: 'GND', 3: '+5V_IN', 4: NC, 5: '3V3A'}),
        C('C107', '1u', '+5V_IN', 'GND'), C('C108', '1u', '3V3A', 'GND'),
        Part('U102', 'Regulator_Linear:AP2112K-3.3', 'AP2112K-3.3', 'SOT235',
             {1: '+5V_IN', 2: 'GND', 3: '+5V_IN', 4: NC, 5: '3V3D'}),
        C('C109', '1u', '+5V_IN', 'GND'), C('C110', '1u', '3V3D', 'GND'), C('C111', '10u', '3V3D', 'GND', 'C0805'),
        Part('U103', 'Regulator_Linear:AP2112K-3.3', 'AP2112K-3.3', 'SOT235',
             {1: '+5V_IN', 2: 'GND', 3: '+5V_IN', 4: NC, 5: '3V3H'}),
        C('C112', '1u', '+5V_IN', 'GND'), C('C113', '1u', '3V3H', 'GND'), C('C114', '10u', '3V3H', 'GND', 'C0805'),
    ]),
    ('Опора 2.5 В (REFIN АЦП, смещение входов, пороги индикаторов)', [
        R('R101', '10', '3V3A', 'REF_IN'), C('C115', '1u', 'REF_IN', 'GND'),
        Part('U104', 'Reference_Voltage:REF3025', 'REF3025', 'SOT23', {1: 'REF_IN', 2: 'REF2V5', 3: 'GND'}),
        C('C116', '1u', 'REF2V5', 'GND'),
    ]),
    ('Контрольные точки', [TP('TP101', '+5V_IN'), TP('TP102', '+15V'), TP('TP103', '-15V'), TP('TP104', '3V3A'),
                           TP('TP105', '3V3D'), TP('TP106', '3V3H'), TP('TP107', 'REF2V5'),
                           TP('TP108', 'GND'), TP('TP109', 'GND')]),
], notes=['C105: «+» на GND, «−» на −15V.  D102 развязывает Tang Nano от АВК при питании по USB (Т-2.2).'])

# --- fpga
_fast = ['i2s_bck', 'i2s_lrck', 'i2s_din', 'adc_sclk', 'pot_sck', 'lcd_sck', 'flash_sck']
tn_pins = {'5V': '5V_TN', 'GND1': 'GND', 'GND2': 'GND'}
_tn = avk_lib.symbols()['Tang_Nano_20K']
for p in kilib.pins(_tn):
    if p[2] in ('5V', 'GND'):
        continue
    sig = p[2].split(' [')[0]
    tn_pins[p[1]] = (sig + '_f') if sig in _fast else sig
sheet('fpga', 'Tang Nano 20K, SPI-флеш прошивки, согласующие резисторы', [
    ('Модуль Tang Nano 20K (гребёнки; номера выводов — HO-01)', [
        Part('A201', f'{CUSTOM_LIB}:Tang_Nano_20K', 'Tang Nano 20K', '', tn_pins)]),
    ('33 Ом в быстрых выходах ПЛИС (у гребёнки)', [
        R(f'R{202 + i}', '33', n + '_f', n) for i, n in enumerate(_fast)]),
    ('SPI NOR флеш: прошивка CPU и калибровки (Т-3.5)', [
        Part('U201', 'Memory_Flash:W25Q32JVSS', 'W25Q64JVSSIQ', 'SO8',
             {1: 'flash_cs_n', 2: 'flash_miso', 3: '3V3D', 4: 'GND', 5: 'flash_mosi', 6: 'flash_sck',
              7: '3V3D', 8: '3V3D'}),
        R('R201', '10k', 'flash_cs_n', '3V3D'), C('C201', '100n', '3V3D', 'GND')]),
    ('Контрольные точки', [TP(f'TP{201 + i}', n) for i, n in enumerate(
        ['i2s_bck', 'i2s_lrck', 'i2s_din', 'adc_sclk', 'adc_sdo1', 'midi_rx', 'sync_in'])]),
], notes=['UART BL702 и слот SD — на плате Tang Nano, на несущую не выводятся.',
          'Выводы A201 с [IOnn] — назначены в .cst (предварительно), остальные — назначить по таблице пинов (план Ж0.1, HO-01).'])

# --- midi_sync
sheet('midi_sync', 'MIDI-вход (TRS) и вход СИНХР', [
    ('MIDI: TRS → мост Шоттки → оптрон H11L1 (Т-4)', [
        Part('J301', 'Connector_Audio:AudioJack3', 'MIDI IN TRS', 'JACK', {'T': 'MIDI_T', 'R': 'MIDI_AC2', 'S': 'MIDI_SHIELD'}),
        R('R301', '220', 'MIDI_T', 'MIDI_AC1'),
        BAT54S('D301', 'MIDI_DCN', 'MIDI_DCP', 'MIDI_AC1'), BAT54S('D302', 'MIDI_DCN', 'MIDI_DCP', 'MIDI_AC2'),
        C('C301', '10n 100V', 'MIDI_SHIELD', 'GND', dnp=True),
        Part('U301', 'Isolator:H11L1', 'H11L1', 'DIP6',
             {1: 'MIDI_DCP', 2: 'MIDI_DCN', 3: NC, 4: 'MIDI_VO', 5: 'GND', 6: '3V3D'}),
        C('C302', '100n', '3V3D', 'GND'), R('R302', '2.2k', 'MIDI_VO', '3V3D'), R('R303', '33', 'MIDI_VO', 'midi_rx')]),
    ('СИНХР: 22 кОм → ограничитель → триггер Шмитта (Т-5)', [
        R('R304', '22k', 'SYNC_RAW', 'SYNC_N'), BAT54S('D303', 'GND', '3V3D', 'SYNC_N'),
        C('C303', '100p', 'SYNC_N', 'GND'), R('R305', '470k', 'SYNC_N', 'GND'),
        Part('U302', '74xGxx:74LVC1G17', '74LVC1G17', 'SOT235', {1: NC, 2: 'SYNC_N', 3: 'GND', 4: 'SYNC_Y', 5: '3V3D'}),
        C('C304', '100n', '3V3D', 'GND'), R('R306', '33', 'SYNC_Y', 'sync_in'),
        TP('TP301', 'SYNC_N'), TP('TP302', 'SYNC_Y')]),
], notes=['Мост D301/D302 делает кабели TRS Type A и Type B равноценными. Экран (S) не заземлять: C301 не устанавливать.'])


# --- ain1 / ain2
def ain(n, base, unit_pins, with_power):
    s, x = f'AIN{n}', base
    parts = [
        R(f'R{x + 1}', '100k 0.1%', f'IN{n}', f'{s}_SUM', 'R0805'),
        R(f'R{x + 2}', '20.0k 0.1%', 'REF2V5', f'{s}_SUM'),
        R(f'R{x + 3}', '24.9k 0.1%', f'{s}_SUM', 'GND'),
        BAT54S(f'D{x + 1}', 'GND', '3V3A', f'{s}_SUM'),
        C(f'C{x + 1}', '1.1n C0G 1%', f'{s}_SUM', f'{s}_OA'),
        R(f'R{x + 4}', '10.0k 0.1%', f'{s}_SUM', f'{s}_P'),
        C(f'C{x + 2}', '560p C0G 1%', f'{s}_P', 'GND'),
        Part('U401', 'Amplifier_Operational:TLV9062', 'OPA2350', 'SO8',
             {unit_pins[0]: f'{s}_P', unit_pins[1]: f'{s}_OA', unit_pins[2]: f'{s}_OA'}),
        R(f'R{x + 5}', '49.9', f'{s}_OA', s),
        C(f'C{x + 3}', '2.2n C0G', s, 'GND'),
        TP(f'TP{x + 1}', s)]
    if with_power:
        parts += [Part('U401', 'Amplifier_Operational:TLV9062', 'OPA2350', 'SO8', {8: '3V3A', 4: 'GND'}),
                  C('C404', '100n', '3V3A', 'GND')]
    return parts


sheet('ain1', 'Входной каскад ВХ1', [
    ('ВХ1: сумматор-сдвиг 0.1·Vin + 1.25 В, ограничитель, ФНЧ Саллена–Ки 20 кГц (Т-6)', ain(1, 400, (3, 2, 1), True))],
    notes=['R1 фильтра = R401‖R402‖R403 = 9.98 кОм (отдельного резистора нет); fc ≈ 20.3 кГц, Q ≈ 0.70.'])
sheet('ain2', 'Входной каскад ВХ2', [
    ('ВХ2: то же, что ВХ1 (второй канал U401)', ain(2, 450, (5, 6, 7), False))])

# --- adc
def adc(ref, vin, sdo, caps):
    c_vdd, c_vdd2, c_vdr, c_ref, c_reg = caps
    return [Part(ref, f'{CUSTOM_LIB}:AD7091R', 'AD7091R', 'MSOP-10',
                 {3: vin, 2: 'REFIN_ADC', 4: f'{ref}_REGCAP', 6: 'adc_convst_n', 7: 'adc_cs_n', 9: 'adc_sclk',
                  8: sdo, 1: '3V3A', 10: '3V3D', 5: 'GND'}),
            C(c_vdd, '100n', '3V3A', 'GND'), C(c_vdd2, '1u', '3V3A', 'GND'),
            C(c_vdr, '100n', '3V3D', 'GND'), C(c_ref, '1u', 'REFIN_ADC', 'GND'),
            C(c_reg, '1u', f'{ref}_REGCAP', 'GND')]


FP['MSOP-10'] = 'Package_SO:MSOP-10_3x3mm_P0.5mm'
sheet('adc', 'АЦП входов: 2 × AD7091R', [
    ('АЦП ВХ1: U501 AD7091R', adc('U501', 'AIN1', 'adc_sdo1', ('C501', 'C502', 'C505', 'C507', 'C509'))),
    ('АЦП ВХ2: U502 AD7091R', adc('U502', 'AIN2', 'adc_sdo2', ('C503', 'C504', 'C506', 'C508', 'C510'))),
    ('Опора АЦП: внешняя REF2V5 (вариант по HO-09)', [R('R501', '0', 'REF2V5', 'REFIN_ADC')]),
], notes=['ВНИМАНИЕ: номера выводов символа AD7091R не проверены — сверить с даташитом (HO-09).',
          'Общие CONVST / CS / SCLK — одновременная выборка (Т-7.1). Номиналы на REFIN и REGCAP — по даташиту.'])

# --- dac
sheet('dac', 'ЦАП PCM5102A', [
    ('ЦАП PCM5102A: I2S, FLT = low latency, SCK на GND (PLL от BCK)', [
        Part('U601', 'Audio:PCM5102A', 'PCM5102A', 'TSSOP20',
             {1: '3V3A', 2: 'DAC_CAPP', 3: 'GND', 4: 'DAC_CAPM', 5: 'DAC_VNEG', 6: 'DAC_OUTL', 7: 'DAC_OUTR',
              8: '3V3A', 9: 'GND', 10: 'GND', 11: '3V3D', 12: 'GND', 13: 'i2s_bck', 14: 'i2s_din', 15: 'i2s_lrck',
              16: 'GND', 17: 'DAC_XSMT', 18: 'DAC_LDOO', 19: 'GND', 20: '3V3D'}),
        C('C601', '100n', '3V3A', 'GND'), C('C602', '10u', '3V3A', 'GND', 'C0805'),
        C('C603', '2.2u', 'DAC_CAPP', 'DAC_CAPM', 'C0603'), C('C604', '2.2u', 'DAC_VNEG', 'GND'),
        C('C607', '100n', '3V3A', 'GND'), C('C608', '10u', '3V3A', 'GND', 'C0805'),
        C('C609', '1u', 'DAC_LDOO', 'GND'),
        C('C610', '100n', '3V3D', 'GND'), C('C611', '10u', '3V3D', 'GND', 'C0805'),
        R('R603', '1k', 'dac_xsmt', 'DAC_XSMT'), R('R604', '10k', 'DAC_XSMT', 'GND')]),
    ('ЦАП: выходные RC (рекомендация даташита)', [
        R('R601', '470', 'DAC_OUTL', 'DAC_L'), C('C605', '2.2n C0G', 'DAC_L', 'GND'),
        R('R602', '470', 'DAC_OUTR', 'DAC_R'), C('C606', '2.2n C0G', 'DAC_R', 'GND'),
        TP('TP601', 'DAC_L'), TP('TP602', 'DAC_R')]),
], notes=['470 Ом с нагрузкой громкости/наушников дают −6.6 % шкалы на ВЫХ — убирается калибровкой (Ж0.3).'])

# --- aout
sheet('aout', 'Выходы ВЫХ, ВЫХ2 и индикаторы перегрузки', [
    ('ГРОМКОСТЬ и ВЫХ: ×4.24, ОС после R704 (Т-9)', [
        Part('RV701', 'Device:R_Potentiometer', '10k A (ГРОМКОСТЬ)', 'POT9', {1: 'GND', 2: 'VOL_W', 3: 'DAC_L'}),
        R('R701', '1k', 'VOL_W', 'OUT1_P'),
        Part('U701', 'Amplifier_Operational:OPA2277', 'OPA2171', 'SO8', {3: 'OUT1_P', 2: 'OUT1_N', 1: 'OUT1_OA'}),
        R('R702', '10.0k 0.1%', 'OUT1_N', 'GND'), R('R703', '32.4k 0.1%', 'OUT1', 'OUT1_N'),
        C('C701', '100p C0G', 'OUT1_OA', 'OUT1_N'), R('R704', '100', 'OUT1_OA', 'OUT1', 'R0805'),
        TP('TP701', 'OUT1')]),
    ('ВЫХ2: ×4.24 без регулятора', [
        R('R705', '1k', 'DAC_R', 'OUT2_P'),
        Part('U701', 'Amplifier_Operational:OPA2277', 'OPA2171', 'SO8', {5: 'OUT2_P', 6: 'OUT2_N', 7: 'OUT2_OA'}),
        R('R706', '10.0k 0.1%', 'OUT2_N', 'GND'), R('R707', '32.4k 0.1%', 'OUT2', 'OUT2_N'),
        C('C702', '100p C0G', 'OUT2_OA', 'OUT2_N'), R('R708', '100', 'OUT2_OA', 'OUT2', 'R0805'),
        TP('TP702', 'OUT2')]),
    ('Питание ОУ и компараторов', [
        Part('U701', 'Amplifier_Operational:OPA2277', 'OPA2171', 'SO8', {8: '+15V', 4: '-15V'}),
        C('C703', '100n', '+15V', 'GND'), C('C704', '100n', '-15V', 'GND'),
        C('C705', '10u 25V', '+15V', 'GND', 'C0805'), C('C706', '10u 25V', '-15V', 'GND', 'C0805'),
        Part('U702', 'Comparator:LM339', 'LM339', 'SO14', {3: '+15V', 12: '-15V'}),
        C('C713', '100n', '+15V', 'GND'), C('C714', '100n', '-15V', 'GND'),
        R('R719', '100', 'REF2V5', 'REF_CMP'), C('C715', '1u', 'REF_CMP', 'GND')]),
    ('Индикатор «+10»: детектор U702 (выв. 2,4,5) → растяжка (выв. 10,11,13) (Т-10)', [
        R('R711', '200k', 'OUT1', 'CMP_PS'), R('R712', '66.5k', 'CMP_PS', 'GND'),
        Part('U702', 'Comparator:LM339', 'LM339', 'SO14', {4: 'CMP_PS', 5: 'REF_CMP', 2: 'CMP_O1'}),
        D('D711', 'Diode:1N4148W', '1N4148W', 'CMP_O1', 'CMP_S1', 'SOD123'),
        R('R715', '100k', 'CMP_S1', '+15V'), C('C711', '1u 25V', 'CMP_S1', 'GND', 'C0805'),
        Part('U702', 'Comparator:LM339', 'LM339', 'SO14', {11: 'CMP_S1', 10: 'GND', 13: 'LED1_K'}),
        D('LED701', 'Device:LED', 'red «+10»', 'LED1_K', 'LED1_A', 'LED3'),
        R('R717', '6.8k', 'LED1_A', 'GND')]),
    ('Индикатор «−10»: детектор U702 (выв. 1,6,7) → растяжка (выв. 8,9,14)', [
        R('R713', '200k', 'OUT1', 'CMP_NS'), R('R714', '49.9k', 'CMP_NS', 'REF_CMP'),
        Part('U702', 'Comparator:LM339', 'LM339', 'SO14', {7: 'CMP_NS', 6: 'GND', 1: 'CMP_O2'}),
        D('D712', 'Diode:1N4148W', '1N4148W', 'CMP_O2', 'CMP_S2', 'SOD123'),
        R('R716', '100k', 'CMP_S2', '+15V'), C('C712', '1u 25V', 'CMP_S2', 'GND', 'C0805'),
        Part('U702', 'Comparator:LM339', 'LM339', 'SO14', {9: 'CMP_S2', 8: 'GND', 14: 'LED2_K'}),
        D('LED702', 'Device:LED', 'red «−10»', 'LED2_K', 'LED2_A', 'LED3'),
        R('R718', '6.8k', 'LED2_A', 'GND')]),
], notes=['LM339 питается от +15V / −15V (вывод 12 «GND» — на −15V): выходы тянут к −15 В, светодиод горит, пока узел S < 0.',
          'Пороги: «+» Vout > +10.02 В, «−» Vout < −10.02 В; растяжка ≈ 66 мс.'])

# --- hp
sheet('hp', 'Выход на наушники / линейный (TPA6132A2)', [
    ('Наушники: вход ×0.5 и разделительные конденсаторы', [
        R('R801', '10k', 'VOL_W', 'HP_IN'), R('R802', '10k', 'HP_IN', 'GND'),
        C('C801', '1u', 'HP_IN', 'HP_INLP', 'C0805'), C('C808', '1u', 'HP_INLM', 'GND', 'C0805'),
        C('C802', '1u', 'HP_IN', 'HP_INRP', 'C0805'), C('C809', '1u', 'HP_INRM', 'GND', 'C0805'),
        TP('TP801', 'HP_IN')]),
    ('Наушники: усилитель TPA6132A2 (Т-9a)', [
        Part('U801', 'Amplifier_Audio:TPA6132A2RTE', 'TPA6132A2', 'WQFN16',
             {2: 'HP_INLP', 1: 'HP_INLM', 3: 'HP_INRP', 4: 'HP_INRM', 16: 'HP_OUTL', 5: 'HP_OUTR',
              13: 'HP_EN', 6: 'HP_G0', 7: 'HP_G1', 14: '3V3H', 12: 'HP_HPVDD', 8: 'HP_HPVSS',
              11: 'HP_CPP', 9: 'HP_CPN', 10: 'GND', 15: 'GND', 17: 'GND'}),
        C('C806', '2.2u', '3V3H', 'GND'), C('C807', '100n', '3V3H', 'GND'),
        C('C804', '1u', 'HP_CPP', 'HP_CPN'), C('C805', '1u', 'HP_HPVSS', 'GND'), C('C810', '1u', 'HP_HPVDD', 'GND'),
        R('R804', '0', 'HP_G0', 'GND'), R('R805', '0', 'HP_G1', 'GND'),
        R('R803', '10k', 'dac_xsmt', 'HP_EN'), C('C803', '1u', 'HP_EN', 'GND')]),
    ('Наушники: гнездо НАУШН./ЛИН.', [
        Part('J801', 'Connector_Audio:AudioJack3', 'НАУШН./ЛИН.', 'JACK', {'T': 'HP_OUTL', 'R': 'HP_OUTR', 'S': 'GND'}),
        Part('D801', 'Device:D_TVS', 'PESD5V0S1BA', 'SOD323', {1: 'HP_OUTL', 2: 'GND'}),
        Part('D802', 'Device:D_TVS', 'PESD5V0S1BA', 'SOD323', {1: 'HP_OUTR', 2: 'GND'})]),
], notes=['Проверить по даташиту TPA6132A2: G0/G1 для 0 дБ, HPVDD (конденсатор на GND или соединение с VDD), '
          'номиналы накачки, полярность EN.',
          'Входы дифференциальные: «+» — сигнал через 1 мкФ, «−» — через 1 мкФ на GND.'])

# --- panel
pots = ['СРЕЗ', 'РЕЗОН.', 'ENV→Ф', 'FX MIX', 'A', 'D', 'S', 'R']
pot_parts = []
for i, nm in enumerate(pots):
    pot_parts += [Part(f'RV{901 + i}', 'Device:R_Potentiometer', f'B10K {nm}', 'POT9',
                       {1: 'GND', 2: f'POT_W{i}', 3: 'MCP_VREF'}),
                  R(f'R{901 + i}', '1k', f'POT_W{i}', f'POT_CH{i}'), C(f'C{901 + i}', '100n', f'POT_CH{i}', 'GND')]
mcp = {i + 1: f'POT_CH{i}' for i in range(8)}
mcp.update({9: 'GND', 10: 'pot_cs_n', 11: 'pot_mosi', 12: 'pot_miso', 13: 'pot_sck', 14: 'GND',
            15: 'MCP_VREF', 16: '3V3A'})
enc_parts = []
for n, nm in enumerate(['МЕНЮ', 'ПАР.1', 'ПАР.2', 'ПАР.3']):
    enc_parts += [Part(f'SW{900 + n}', 'Device:RotaryEncoder_Switch', f'EC11 {nm}', 'EC11',
                       {'A': f'ENC{n}_A', 'B': f'ENC{n}_B', 'C': 'GND', 'S1': f'ENC{n}_S', 'S2': 'GND'})]
    for k, (pre, rtl) in enumerate([('A', 'enc_a'), ('B', 'enc_b'), ('S', 'enc_sw')]):
        enc_parts += [R(f'R{920 + 10 * k + n}', '10k', f'ENC{n}_{pre}', '3V3D'),
                      R(f'R{950 + 10 * k + n}', '10k', f'ENC{n}_{pre}', f'{rtl}{n}'),
                      C(f'C{920 + 10 * k + n}', '10n', f'{rtl}{n}', 'GND')]
sheet('panel', 'Панель: потенциометры, MCP3208, энкодеры, дисплей, штыри', [
    ('Потенциометры (Т-11): верх — MCP_VREF, ратиометрично', pot_parts),
    ('MCP3208', [Part('U901', 'Analog_ADC:MCP3208', 'MCP3208', 'SO16', mcp),
                 C('C909', '100n', '3V3A', 'GND'), C('C910', '1u', '3V3A', 'GND'),
                 R('R909', '10', '3V3A', 'MCP_VREF'), C('C911', '1u', 'MCP_VREF', 'GND'),
                 R('R910', '10k', 'pot_cs_n', '3V3D')]),
    ('Энкодеры EC11 (Т-12): подтяжки 10 кОм, RC 10 кОм / 10 нФ', enc_parts),
    ('Дисплей 1.14″ ST7789 (Т-13)', [
        Part('J901', 'Connector_Generic:Conn_01x08', 'LCD ST7789', 'PS1x8',
             {1: 'GND', 2: '3V3D', 3: 'lcd_sck', 4: 'lcd_mosi', 5: 'lcd_rst_n', 6: 'lcd_dc', 7: 'lcd_cs_n', 8: 'LCD_BLK'}),
        R('R911', '100', 'lcd_bl', 'LCD_BLK'), C('C912', '10u', '3V3D', 'GND', 'C0805'), C('C913', '100n', '3V3D', 'GND')]),
    ('Панельные штыри 2РМТ (провод к плате)', [
        Part('J911', 'Connector_Generic:Conn_01x01', 'ВХ1', 'WIRE', {1: 'IN1'}),
        Part('J912', 'Connector_Generic:Conn_01x01', 'ВХ2', 'WIRE', {1: 'IN2'}),
        Part('J913', 'Connector_Generic:Conn_01x01', 'ВЫХ', 'WIRE', {1: 'OUT1'}),
        Part('J914', 'Connector_Generic:Conn_01x01', 'ВЫХ2', 'WIRE', {1: 'OUT2'})]),
], notes=['Порядок выводов J901 — по выбранному модулю дисплея. Если вход BLK — анод подсветки, а не логический, '
          'нужен ключ (Т-13.2).', 'Порядок каналов MCP3208 = порядок ручек в прошивке.'])




def merge(name, title, names):
    groups, notes = [], []
    for n in names:
        sh = SHEETS.pop(n)
        groups += sh['groups']
        notes += sh['notes']
    SHEETS[name] = dict(title=title, groups=groups, notes=notes)


merge('analog_in', 'Аналоговые входы ВХ1, ВХ2 и АЦП', ['ain1', 'ain2', 'adc'])
merge('audio_out', 'ЦАП, выходы ВЫХ / ВЫХ2, индикаторы перегрузки', ['dac', 'aout'])
merge('phones', 'Выход на наушники / линейный (TPA6132A2)', ['hp'])
for _n in ('power', 'fpga', 'midi_sync', 'analog_in', 'audio_out', 'phones', 'panel'):
    SHEETS.move_to_end(_n)


# ------------------------------------------------------------------ символы
SYMDEFS = {}     # lib_id -> flat symbol
CUSTOM = avk_lib.symbols()


def symdef(lib_id):
    if lib_id not in SYMDEFS:
        lib, name = lib_id.split(':')
        if lib == CUSTOM_LIB:
            s = list(CUSTOM[name])
            s[1] = lib_id
            SYMDEFS[lib_id] = s
        else:
            SYMDEFS[lib_id] = kilib.flat_symbol(lib, name)
    return SYMDEFS[lib_id]


def pin_table(lib_id):
    """номер -> (unit, x, y, angle, etype); и имя -> номер для ссылок по имени."""
    t = {}
    for (u, num, name, x, y, a, ln, et) in kilib.pins(symdef(lib_id)):
        t[num] = (u or 1, x, y, a, et)
    return t


# ------------------------------------------------------------------ раскладка
G = 2.54
CH = 1.15          # ширина символа шрифта 1.27 мм (оценка)
STUB = 2.54


def snap(v):
    return round(v / G) * G


def body_bbox(lib_id, unit):
    """Габарит графики юнита (мм, координаты библиотеки)."""
    xs, ys = [], []
    for sub in kilib.find(symdef(lib_id), 'symbol'):
        u = int(sub[1].rsplit('_', 2)[-2])
        if u not in (0, unit):
            continue
        for g in sub[2:]:
            if not isinstance(g, list):
                continue
            for k in ('start', 'end', 'center', 'at'):
                e = get(g, k)
                if e and g[0] != 'pin':
                    xs.append(float(e[1]))
                    ys.append(float(e[2]))
            pts = get(g, 'pts')
            if pts:
                for xy in kilib.find(pts, 'xy'):
                    xs.append(float(xy[1]))
                    ys.append(float(xy[2]))
            if g[0] == 'pin':
                at = get(g, 'at')
                xs.append(float(at[1]))
                ys.append(float(at[2]))
    return min(xs), max(xs), min(ys), max(ys)


HORIZ2 = {'Diode:SS14', 'Diode:1N4148W', 'Device:LED', 'Device:D_TVS'}
ROTATE = {'Device:R', 'Device:C', 'Device:C_Polarized', 'Device:FerriteBead'}


def xf(px, py, r):
    """Точка библиотеки (Y вверх) -> смещение на листе (Y вниз) при повороте r (CCW)."""
    if r == 90:
        return -py, -px
    return px, -py


class Inst:
    """Размещаемый юнит детали."""

    def __init__(self, part, unit, pins):
        self.part, self.unit, self.pins = part, unit, pins   # pins: num -> net
        self.rot = 90 if part.lib in ROTATE else 0

    def body(self):
        """Габарит тела на листе относительно точки привязки: x0, x1, y0(верх), y1(низ)."""
        bx0, bx1, by0, by1 = body_bbox(self.part.lib, self.unit)
        pts = [xf(x, y, self.rot) for x in (bx0, bx1) for y in (by0, by1)]
        return min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts)

    def pin_pos(self, pt, num):
        _, px, py, a, _ = pt[num]
        dx, dy = xf(px, py, self.rot)
        return dx, dy, int(a + self.rot) % 360

    def extents(self, pt):
        """Габарит с метками и подписями: левый, правый, верхний, нижний край (Y вниз)."""
        x0, x1, y0, y1 = self.body()
        L, R_, T, B = x0, x1, y0, y1
        for num, net in self.pins.items():
            px, py, a = self.pin_pos(pt, num)
            ln = STUB + (len(net) * CH + 3 if net not in ('GND', NC) else 7.6)
            if a == 0:
                L = min(L, px - ln)
            elif a == 180:
                R_ = max(R_, px + ln)
            elif a == 90:
                B = max(B, py + ln)
            else:
                T = min(T, py - ln)
        txt = max(len(self.part.ref), len(self.part.value)) * CH
        mode = self.field_mode(pt)
        if mode == 'center':    # подписи над и под телом, по центру
            T, B = min(T, y0 - 5), max(B, y1 + 5)
            L, R_ = min(L, -txt / 2), max(R_, txt / 2)
        elif mode == 'above':
            T = min(T, y0 - 6)
            R_ = max(R_, x0 + txt)
        elif mode == 'below':
            B = max(B, y1 + 6)
            R_ = max(R_, x0 + txt)
        else:                   # справа от меток
            R_ = R_ + 1.5 + txt
        return L, R_, T, B

    def field_mode(self, pt):
        if self.rot == 90 or self.part.lib in HORIZ2:
            return 'center'
        angs = {self.pin_pos(pt, n)[2] for n in pt if pt[n][0] in (self.unit, 0)}
        if 270 not in angs:
            return 'above'
        if 90 not in angs:
            return 'below'
        return 'right'


def label_text(net):
    return net


def layout_block(parts, maxw):
    """Раскладка деталей блока рядами. Возвращает [(inst, rx, ry, ex0, ey0)], ширину, высоту."""
    out, x, y, rowh, right = [], 0.0, 0.0, 0.0, 0.0
    for part in parts:
        pt = pin_table(part.lib)
        byunit = defaultdict(dict)
        for num, net in part.pins.items():
            if num not in pt:
                raise KeyError(f'{part.ref}: нет вывода {num} в {part.lib}')
            byunit[pt[num][0]][num] = net
        for unit, pins in sorted(byunit.items()):
            inst = Inst(part, unit, pins)
            ex0, ex1, ey0, ey1 = inst.extents(pt)
            w, h = ex1 - ex0, ey1 - ey0
            if x + w > maxw and x > 0:
                x, y, rowh = 0.0, y + rowh + 5, 0.0
            out.append((inst, x, y, ex0, ey0))
            x += w + 5
            right = max(right, x - 5)
            rowh = max(rowh, h)
    return out, right, y + rowh


BLOCK_W = 185.0


def plan_sheet(sh, page_w, page_h, block_w=185.0):
    """Блоки (группы) раскладываются полками; детали внутри блока — рядами."""
    placed, frames = [], []
    top = 22.0 + 4.0 * len(sh['notes'])
    x, y, shelf = 17.0, top, 0.0
    for gtitle, parts in sh['groups']:
        insts, bw, bh = layout_block(parts, min(block_w, page_w - 30))
        fw, fh = max(bw, len(gtitle) * 1.7) + 6, bh + 11
        if x + fw > page_w - 12 and x > 17.0:
            x, y, shelf = 17.0, y + shelf + 6, 0.0
        for inst, rx, ry, ex0, ey0 in insts:
            placed.append((inst, snap(x + 3 + rx - ex0) + G, snap(y + 8 + ry - ey0) + G))
        frames.append((gtitle, x, y, x + fw, y + fh))
        x += fw + 6
        shelf = max(shelf, fh)
    return placed, frames, y + shelf


# ------------------------------------------------------------------ вывод S-выражений
def eff(size=1.27, justify=None, hide=False, bold=False):
    f = [S('font'), [S('size'), size, size]]
    if bold:
        f.append(S('bold'))
    e = [S('effects'), f]
    if justify:
        e.append([S('justify')] + [S(j) for j in justify])
    if hide:
        e.append(S('hide'))
    return e


def prop(name, val, x, y, ang=0, hide=False, justify=None):
    return [S('property'), name, val, [S('at'), x, y, ang], eff(justify=justify, hide=hide)]


def wire(x1, y1, x2, y2, key):
    return [S('wire'), [S('pts'), [S('xy'), x1, y1], [S('xy'), x2, y2]],
            [S('stroke'), [S('width'), 0], [S('type'), S('default')]], [S('uuid'), uid('w', *key)]]


def text(t, x, y, size=1.27, key=(), bold=False):
    return [S('text'), t, [S('at'), x, y, 0], eff(size, justify=['left', 'bottom'], bold=bold),
            [S('uuid'), uid('t', t, x, y, *key)]]


DIRS = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}   # от точки подключения наружу (экран, Y вниз)
LBL_ANG = {(-1, 0): 180, (1, 0): 0, (0, 1): 270, (0, -1): 90}
GND_ANG = {(0, 1): 0, (0, -1): 180, (1, 0): 90, (-1, 0): 270}


def render_sheet(name, sh, root_uuid, sheet_uuid, global_nets, page):
    best = None
    for paper, pw, ph in (('A3', 410.0, 255), ('A2', 584.0, 375), ('A1', 831.0, 545)):
        for bw in (185.0, 150.0, 230.0, 125.0, 280.0):
            placed, titles, height = plan_sheet(sh, pw, ph, bw)
            if height < ph:
                best = (paper, placed, titles)
                break
        if best:
            break
    paper, placed, titles = best
    items, libs_used, pwr_count = [], set(), [0]
    path = f'/{root_uuid}/{sheet_uuid}'
    for t, x0, y0, x1, y1 in titles:
        items.append(text(t, x0 + 2, y0 + 3.5, 1.8, key=(name,), bold=True))
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        items.append([S('polyline'), [S('pts')] + [[S('xy'), a, b] for a, b in pts],
                      [S('stroke'), [S('width'), 0.3], [S('type'), S('dash')], [S('color'), 72, 72, 160, 1]],
                      [S('uuid'), uid('frame', name, t)]])
    items.append(text(sh['title'], 20, 17, 2.5, key=(name, 'title'), bold=True))
    for i, n in enumerate(sh['notes']):
        items.append(text(n, 20, 22 + i * 4, 1.5, key=(name, 'note')))

    def power_sym(lib_id, value, x, y, ang, key):
        libs_used.add(lib_id)
        pwr_count[0] += 1
        ref = f'#PWR{page:02d}{pwr_count[0]:03d}'
        return [S('symbol'), [S('lib_id'), lib_id], [S('at'), x, y, ang], [S('unit'), 1],
                [S('in_bom'), S('yes')], [S('on_board'), S('yes')], [S('dnp'), S('no')],
                [S('uuid'), uid('pwr', name, *key)],
                prop('Reference', ref, x, y + 6, hide=True), prop('Value', value, x, y + 3.8, hide=(value == 'GND')),
                prop('Footprint', '', x, y, hide=True), prop('Datasheet', '', x, y, hide=True),
                [S('pin'), '1', [S('uuid'), uid('pwrpin', name, *key)]],
                [S('instances'), [S('project'), PROJECT, [S('path'), path, [S('reference'), ref], [S('unit'), 1]]]]]

    for inst, X, Y in placed:
        part = inst.part
        libs_used.add(part.lib)
        pt = pin_table(part.lib)
        is_flag = part.ref.startswith('#')
        sym = [S('symbol'), [S('lib_id'), part.lib], [S('at'), X, Y, inst.rot], [S('unit'), inst.unit],
               [S('in_bom'), S('no' if is_flag else 'yes')], [S('on_board'), S('no' if is_flag else 'yes')],
               [S('dnp'), S('yes' if part.dnp else 'no')], [S('uuid'), uid('sym', part.ref, inst.unit)]]
        x0, x1, y0, y1 = inst.body()
        mode = inst.field_mode(pt)
        if mode == 'center':
            rp = (X, Y + y0 - 1.2, None)
            vp = (X, Y + y1 + 2.4, None)
        elif mode == 'above':
            rp = (X + x0, Y + y0 - 3.6, ['left'])
            vp = (X + x0, Y + y0 - 1.3, ['left'])
        elif mode == 'below':
            rp = (X + x0, Y + y1 + 2.4, ['left'])
            vp = (X + x0, Y + y1 + 4.7, ['left'])
        else:
            ex = inst.extents(pt)
            rp = (X + ex[1] - max(len(part.ref), len(part.value)) * CH, Y + y0 + 1.5, ['left'])
            vp = (rp[0], Y + y0 + 3.6, ['left'])
        fa = inst.rot
        sym += [prop('Reference', part.ref, rp[0], rp[1], fa, hide=is_flag, justify=rp[2]),
                prop('Value', part.value, vp[0], vp[1], fa, justify=vp[2]),
                prop('Footprint', part.fp, X, Y, hide=True), prop('Datasheet', '~', X, Y, hide=True)]
        for num in sorted(pt):
            if pt[num][0] == inst.unit or pt[num][0] == 0:
                sym.append([S('pin'), num, [S('uuid'), uid('pin', part.ref, num)]])
        sym.append([S('instances'), [S('project'), PROJECT,
                                     [S('path'), path, [S('reference'), part.ref], [S('unit'), inst.unit]]]])
        items.append(sym)
        for num, net in inst.pins.items():
            px, py, a = inst.pin_pos(pt, num)
            cx, cy = X + px, Y + py
            if net == NC:
                items.append([S('no_connect'), [S('at'), cx, cy], [S('uuid'), uid('nc', part.ref, num)]])
                continue
            dx, dy = DIRS[int(a) % 360]
            st = 2 * STUB if (net == 'GND' and dy == 0) else STUB
            ex, ey = cx + dx * st, cy + dy * st
            items.append(wire(cx, cy, ex, ey, (part.ref, num)))
            key = (part.ref, num)
            if net == 'GND':
                items.append(power_sym('power:GND', 'GND', ex, ey, GND_ANG[(dx, dy)], key))
            elif net in global_nets:
                ang = LBL_ANG[(dx, dy)]
                items.append([S('global_label'), net, [S('shape'), S('passive')], [S('at'), ex, ey, ang],
                              [S('fields_autoplaced')],
                              eff(justify=['right'] if ang in (180, 270) else ['left']),
                              [S('uuid'), uid('gl', *key)],
                              [S('property'), 'Intersheetrefs', '${INTERSHEET_REFS}', [S('at'), ex, ey, 0],
                               eff(size=1.27, hide=True)]])
            else:
                ang = LBL_ANG[(dx, dy)]
                items.append([S('label'), net, [S('at'), ex, ey, ang], [S('fields_autoplaced')],
                              eff(justify=['right', 'bottom'] if ang in (180, 270) else ['left', 'bottom']),
                              [S('uuid'), uid('lb', *key)]])
    libsyms = [symdef(l) for l in sorted(libs_used)]
    doc = [S('kicad_sch'), [S('version'), 20230121], [S('generator'), S('eeschema')],
           [S('uuid'), sheet_uuid], [S('paper'), paper],
           [S('title_block'), [S('title'), sh['title']], [S('date'), '2026-10-03'], [S('rev'), '0.1'],
            [S('company'), 'АВК-6 «Музыкальная пауза»'],
            [S('comment'), 1, 'Сгенерировано hw/kicad/tools/gen_kicad.py по hw/schematic.md'],
            [S('comment'), 2, 'Метки цепей; связи между листами — глобальные метки']],
           [S('lib_symbols')] + libsyms] + items
    return doc


def power_lib():
    for n in ('GND', 'PWR_FLAG'):
        symdef(f'power:{n}')


def main():
    power_lib()
    # глобальные цепи: встречаются на нескольких листах
    where = defaultdict(set)
    for name, sh in SHEETS.items():
        for _, parts in sh['groups']:
            for p in parts:
                for net in p.pins.values():
                    where[net].add(name)
    global_nets = {n for n, s in where.items() if len(s) > 1 and n not in ('GND', NC)}
    root_uuid = uid('root')
    sheets_sx = []
    for i, (name, sh) in enumerate(SHEETS.items()):
        su = uid('sheet', name)
        doc = render_sheet(name, sh, root_uuid, su, global_nets, i + 2)
        with open(os.path.join(OUT, f'{name}.kicad_sch'), 'w', encoding='utf-8') as f:
            f.write(dump(doc) + '\n')
        col, row = i % 4, i // 4
        x, y = 20 + col * 95, 40 + row * 45
        sheets_sx.append([S('sheet'), [S('at'), x, y], [S('size'), 80, 30], [S('fields_autoplaced')],
                          [S('stroke'), [S('width'), 0.1524], [S('type'), S('solid')]],
                          [S('fill'), [S('color'), 0, 0, 0, 0.0]], [S('uuid'), su],
                          prop('Sheetname', name, x, y - 0.7, justify=['left', 'bottom']),
                          prop('Sheetfile', f'{name}.kicad_sch', x, y + 30.6, justify=['left', 'top']),
                          [S('instances'), [S('project'), PROJECT, [S('path'), f'/{root_uuid}', [S('page'), str(i + 2)]]]]])
        sheets_sx.append(text(sh['title'], x + 2, y + 16, 1.5, key=('root', name)))
    root = [S('kicad_sch'), [S('version'), 20230121], [S('generator'), S('eeschema')],
            [S('uuid'), root_uuid], [S('paper'), 'A3'],
            [S('title_block'), [S('title'), 'Несущая плата FPGA-синтезатора АВК-6'], [S('date'), '2026-10-03'],
             [S('rev'), '0.1'], [S('company'), 'АВК-6 «Музыкальная пауза»'],
             [S('comment'), 1, 'Сгенерировано hw/kicad/tools/gen_kicad.py']],
            [S('lib_symbols')],
            text('Несущая плата FPGA-синтезатора АВК-6 — листы схемы', 20, 25, 3, key=('root',), bold=True),
            text('Описание узлов, расчёты и номиналы: hw/schematic.md.  Открытые вопросы: HO-01 (выводы Tang Nano), '
                 'HO-06 (нижний разъём), HO-09 (AD7091R).', 20, 30, 1.6, key=('root', 'n'))] + sheets_sx + \
           [[S('sheet_instances'), [S('path'), '/', [S('page'), '1']]]]
    with open(os.path.join(OUT, f'{PROJECT}.kicad_sch'), 'w', encoding='utf-8') as f:
        f.write(dump(root) + '\n')
    with open(os.path.join(OUT, f'{CUSTOM_LIB}.kicad_sym'), 'w', encoding='utf-8') as f:
        f.write(avk_lib.library_text())
    with open(os.path.join(OUT, 'sym-lib-table'), 'w') as f:
        f.write('(sym_lib_table\n  (version 7)\n  (lib (name "%s")(type "KiCad")(uri "${KIPRJMOD}/%s.kicad_sym")'
                '(options "")(descr "АВК-6: AD7091R, Tang Nano 20K"))\n)\n' % (CUSTOM_LIB, CUSTOM_LIB))
    pro = os.path.join(OUT, f'{PROJECT}.kicad_pro')
    if not os.path.exists(pro):
        with open(pro, 'w') as f:
            f.write('{\n  "meta": {"filename": "%s.kicad_pro", "version": 1},\n  "schematic": {},\n'
                    '  "sheets": [],\n  "boards": [],\n  "libraries": {"pinned_footprint_libs": [], '
                    '"pinned_symbol_libs": []}\n}\n' % PROJECT)
    # сводка для проверки
    nets = defaultdict(list)
    for name, sh in SHEETS.items():
        for _, parts in sh['groups']:
            for p in parts:
                for num, net in p.pins.items():
                    nets[net].append(f'{p.ref}.{num}')
    with open(os.path.join(OUT, 'tools', 'expected_nets.txt'), 'w') as f:
        for n in sorted(nets):
            f.write(f'{n}: {" ".join(sorted(nets[n]))}\n')
    print('листов:', len(SHEETS), 'глобальных цепей:', len(global_nets))


if __name__ == '__main__':
    main()
