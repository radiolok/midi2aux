"""Checks the images written by test_fat with the independent reader in tools/fatimg.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fatimg  # noqa: E402

d = Path(sys.argv[1])
for bits in (16, 32):
    f = fatimg.Fat(bytearray((d / f"out{bits}.img").read_bytes()))
    f.check()
    pat = bytes((i * 7 + bits) & 0xFF for i in range(5000))
    assert f.read("NEW.TXT") == pat
    assert f.read("HELLO.TXT") == pat[100:1600]
    assert f.read("BIG.BIN") == b"small"
    assert f.read("EMPTY") == b""
    print(f"fat{bits}: image ok")
