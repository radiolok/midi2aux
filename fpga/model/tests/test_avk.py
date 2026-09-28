import numpy as np

from synthmodel import analysis, avk

FS_IN = 99e6 / 512
FS = FS_IN / 4


def decimate(x):
    d = avk.Decimator()
    return np.array([y for v in x if (y := d.push(v)) is not None])


def test_adc_calibration():
    assert avk.adc_to_q16(2048) == 0
    assert avk.adc_to_q16(4095) == 81880          # +12.5 V ~ 1.25 МЕ
    assert avk.adc_to_q16(0) == -81920
    code = avk.volts_to_code(10.0)                # 1 МЕ
    assert abs(avk.adc_to_q16(code) - 65536) <= 40


def test_decimator_passband_and_stopband():
    n = int(0.2 * FS_IN)
    t = np.arange(n) / FS_IN
    for f, lo, hi in ((1000, 0.99, 1.01), (10000, 0.95, 1.01), (30000, 0, 10 ** (-60 / 20)),
                      (60000, 0, 10 ** (-60 / 20))):
        x = np.round(40000 * np.sin(2 * np.pi * f * t)).astype(int)
        y = decimate(x)[200:] / 40000
        amp = np.sqrt(2) * np.std(y)
        assert lo <= amp <= hi, (f, amp)


def test_decimator_dc_gain():
    y = decimate([30000] * 1000)
    assert abs(y[-1] - 30000) <= 30000 * 0.002


def test_math_ops():
    one = 1 << 16
    assert avk.math_op(avk.MUL, one // 2, one // 2) == one // 4      # AVK: 5 V * 5 V / 10 V = 2.5 V
    assert avk.math_op(avk.MUL, -one, one) == -one
    assert avk.math_op(avk.DIV, one // 2, one) == one // 2
    assert avk.math_op(avk.DIV, one, one // 4) == (1 << 17) - 1      # saturated
    assert avk.math_op(avk.DIV, -one, 0) == -(1 << 17)
    assert avk.math_op(avk.ABS, -12345, 0) == 12345
    assert avk.math_op(avk.ADD, 100000, 100000) == (1 << 17) - 1
    assert avk.math_op(avk.SUB, -100000, 100000) == -(1 << 17)
    assert avk.math_op(avk.MIN, 5, -7) == -7 and avk.math_op(avk.MAX, 5, -7) == 5
    assert avk.math_op(avk.MOD, 70000, 30000) == 10000
    assert avk.math_op(avk.MOD, -70000, 30000) == -10000
    assert avk.math_op(avk.AXPB, one, 1000, k=-2 * one) == -2 * one + 1000


def test_bus_order_and_mixer():
    b = avk.AvkBus()
    b.slots[0].param[0] = avk.ADD
    b.slots[0].sel_a, b.slots[0].sel_b = avk.S_IN1, 9     # reads slot 1: previous sample
    b.slots[1].param[0] = avk.MUL
    b.slots[1].sel_a, b.slots[1].sel_b = avk.S_IN1, avk.S_IN2
    b.gain = [0] * b.n
    b.gain[8] = 1 << 16
    one = 1 << 16
    out, _ = b.sample(0, one // 2, one // 2, 0, 0, 0, 0, 0)
    assert b.s[9] == one // 4 and out == one // 2              # slot 1 was 0 when slot 0 ran
    out, out2 = b.sample(0, one // 2, one // 2, 12345, 0, 1, 0, 1)
    assert out == one // 2 + one // 4 and out2 == 12345
    assert b.s[avk.S_SYNC] == one and b.s[avk.S_GATE] == one
    b.gain[avk.S_IN1] = 4 << 16                                 # overdrive: soft clipped at 1.25 МЕ
    out, _ = b.sample(0, one, 0, 0, 0, 0, 0, 0)
    assert 65536 < out <= 81920
