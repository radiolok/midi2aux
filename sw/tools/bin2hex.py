#!/usr/bin/env python3
"""Raw binary -> $readmemh file of 32-bit little-endian words (BSRAM init)."""
import argparse
import sys
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("bin", type=Path)
p.add_argument("hex", type=Path)
p.add_argument("--words", type=int, default=0, help="pad with zeros to this many words")
a = p.parse_args()

data = a.bin.read_bytes()
data += b"\0" * (-len(data) % 4)
words = [int.from_bytes(data[i:i + 4], "little") for i in range(0, len(data), 4)]
if a.words:
    if len(words) > a.words:
        sys.exit(f"{a.bin}: {len(words)} words do not fit into {a.words}")
    words += [0] * (a.words - len(words))
a.hex.write_text("".join(f"{w:08x}\n" for w in words))
