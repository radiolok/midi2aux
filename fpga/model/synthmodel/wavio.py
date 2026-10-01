"""WAV I/O for integer PCM, 16/24/32 bit (scipy cannot write 24-bit)."""

import struct

import numpy as np


def write_wav(path, fs_hz: int, channels, bits: int = 24) -> None:
    """channels: list of int arrays already scaled to `bits` (full scale 2**(bits-1))."""
    data = np.stack([np.asarray(c, dtype=np.int64) for c in channels], axis=1)
    lim = 1 << (bits - 1)
    data = np.clip(data, -lim, lim - 1)
    nch = data.shape[1]
    nbytes = bits // 8
    raw = data.astype("<i4").view(np.uint8).reshape(-1, 4)[:, :nbytes].tobytes()
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(raw)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 1, nch, int(fs_hz),
                                      int(fs_hz) * nch * nbytes, nch * nbytes, bits))
        f.write(b"data" + struct.pack("<I", len(raw)) + raw)


def write_float(path, fs_hz: int, channels, bits: int = 24) -> None:
    """Float channels in [-1, 1] -> integer PCM."""
    scale = (1 << (bits - 1)) - 1
    write_wav(path, fs_hz, [np.round(np.asarray(c) * scale) for c in channels], bits)


def read_wav(path):
    """(fs, int array [n, channels] right-aligned, bits) for integer PCM WAV."""
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError(f"{path}: not a RIFF/WAVE file")
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(raw):
        cid, size = raw[pos:pos + 4], struct.unpack("<I", raw[pos + 4:pos + 8])[0]
        body = raw[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", body[:16])
        elif cid == b"data":
            data = body
        pos += 8 + size + (size & 1)
    if fmt is None or data is None or fmt[0] != 1:
        raise ValueError(f"{path}: no integer PCM data")
    _, nch, fs, _, _, bits = fmt
    nbytes = bits // 8
    b = np.frombuffer(data, dtype=np.uint8).reshape(-1, nbytes)
    word = np.zeros((len(b), 4), dtype=np.uint8)
    word[:, 4 - nbytes:] = b  # left-align in int32, then shift back with sign
    vals = word.view("<i4").reshape(-1).astype(np.int64) >> (32 - bits)
    return fs, vals.reshape(-1, nch), bits
