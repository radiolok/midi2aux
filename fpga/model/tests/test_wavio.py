import numpy as np
import pytest

from synthmodel import wavio


@pytest.mark.parametrize("bits", [16, 24, 32])
def test_roundtrip(tmp_path, bits):
    rng = np.random.default_rng(0)
    lim = 1 << (bits - 1)
    ch = [rng.integers(-lim, lim, 1000), np.array([-lim, lim - 1, 0, -1] * 250)]
    p = tmp_path / "t.wav"
    wavio.write_wav(p, 48_000, ch, bits)
    fs, data, b = wavio.read_wav(p)
    assert (fs, b) == (48_000, bits)
    assert np.array_equal(data[:, 0], ch[0]) and np.array_equal(data[:, 1], ch[1])
