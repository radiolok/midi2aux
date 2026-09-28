import math

from synthmodel import softclip


def test_linear_below_knee():
    for x in (0, 1, -1, 30000, -65536, 65536):
        assert softclip.softclip(x) == x


def test_knee_smooth_and_bounded():
    prev = softclip.softclip(65536)
    for x in range(65537, 65536 * 8, 97):
        y = softclip.softclip(x)
        assert prev <= y <= softclip.L
        assert y - prev <= 97  # slope <= 1
        ideal = 65536 + 16384 * math.tanh(min((x - 65536) / 16384, 4.0))  # knee ends at u = 4
        assert abs(y - ideal) < 4  # floor in interpolation and >> 2
        prev = y
    assert softclip.softclip(10**7) == 65536 + (softclip._LAST >> 2) <= softclip.L
    assert softclip.softclip(-(10**7)) == -softclip.softclip(10**7)
