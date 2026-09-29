#!/usr/bin/env python3
"""FAT16 / FAT32 disk images for tests (independent of the firmware's fw/fat.c).

  fatimg.py make IMG {16|32} [NAME=PATH ...] [--frag] [--lfn]   MBR + one partition, files in the root
  fatimg.py cat IMG NAME                                        print a root file (8.3 name) to stdout
  fatimg.py check IMG                                           consistency: FAT copies, chains, sizes
Only what the tests need: 512-byte sectors, root directory, 8.3 names (LFN entries are skipped).
"""

import struct
import sys

SECTOR = 512


def name83(name):
    base, _, ext = name.upper().partition(".")
    return (base.ljust(8)[:8] + ext.ljust(3)[:3]).encode("ascii")


class Fat:
    def __init__(self, data):
        self.d = data
        # MBR partition 1 (or a superfloppy)
        if data[510:512] == b"\x55\xAA" and data[0x1C2] in (0x04, 0x06, 0x0B, 0x0C, 0x0E):
            self.part = struct.unpack_from("<I", data, 0x1C6)[0] * SECTOR
        else:
            self.part = 0
        b = self.part
        (self.bps, self.spc, self.rsv, self.nfats, self.rootents, tot16, _, fatsz16, _, _, _,
         tot32) = struct.unpack_from("<HBHBHHBHHHII", data, b + 11)
        assert self.bps == SECTOR
        fatsz = fatsz16 or struct.unpack_from("<I", data, b + 36)[0]
        self.fatsz = fatsz
        self.tot = tot16 or tot32
        self.fat0 = b + self.rsv * SECTOR
        self.root_secs = (self.rootents * 32 + SECTOR - 1) // SECTOR
        self.root0 = self.fat0 + self.nfats * fatsz * SECTOR
        self.data0 = self.root0 + self.root_secs * SECTOR
        nclus = (self.tot - self.rsv - self.nfats * fatsz - self.root_secs) // self.spc
        self.nclus = nclus
        self.fat32 = nclus >= 65525
        self.root_clus = struct.unpack_from("<I", data, b + 44)[0] if self.fat32 else 0
        self.csize = self.spc * SECTOR

    def fat_get(self, n, copy=0):
        off = self.fat0 + copy * self.fatsz * SECTOR
        if self.fat32:
            return struct.unpack_from("<I", self.d, off + 4 * n)[0] & 0x0FFFFFFF
        return struct.unpack_from("<H", self.d, off + 2 * n)[0]

    def eoc(self, v):
        return v >= (0x0FFFFFF8 if self.fat32 else 0xFFF8)

    def chain(self, c):
        out = []
        while 2 <= c and not self.eoc(c):
            out.append(c)
            assert len(out) <= self.nclus, "FAT loop"
            c = self.fat_get(c)
        return out

    def clus_off(self, c):
        return self.data0 + (c - 2) * self.csize

    def root_entries(self):
        if self.fat32:
            for c in self.chain(self.root_clus):
                for i in range(0, self.csize, 32):
                    yield self.clus_off(c) + i
        else:
            for i in range(self.rootents):
                yield self.root0 + 32 * i

    def files(self):
        for off in self.root_entries():
            e = self.d[off:off + 32]
            if e[0] == 0:
                return
            if e[0] == 0xE5 or e[11] == 0x0F or e[11] & 0x08:
                continue
            clus = struct.unpack_from("<H", e, 26)[0] | (struct.unpack_from("<H", e, 20)[0] << 16)
            yield e[:11], clus, struct.unpack_from("<I", e, 28)[0], e[11]

    def read(self, name):
        for n, clus, size, _ in self.files():
            if n == name83(name):
                data = b"".join(self.d[self.clus_off(c):self.clus_off(c) + self.csize] for c in self.chain(clus))
                return data[:size]
        raise FileNotFoundError(name)

    def check(self):
        for k in range(1, self.nfats):
            a = self.d[self.fat0:self.fat0 + self.fatsz * SECTOR]
            b = self.d[self.fat0 + k * self.fatsz * SECTOR:self.fat0 + (k + 1) * self.fatsz * SECTOR]
            assert a == b, "FAT copies differ"
        used = set()
        for n, clus, size, attr in self.files():
            ch = self.chain(clus) if clus else []
            assert len(ch) == (size + self.csize - 1) // self.csize, (n, len(ch), size)
            assert not used & set(ch), f"cross-linked {n}"
            used |= set(ch)
        if self.fat32:
            used |= set(self.chain(self.root_clus))
        for c in range(2, self.nclus + 2):
            if self.fat_get(c) != 0:
                assert c in used, f"lost cluster {c}"
        return True


def make(path, fat_type, files, frag=False, lfn=False):
    if fat_type == 16:
        total, spc, rsv, rootents = 65536, 4, 4, 512                     # 32 MB
    else:
        total, spc, rsv, rootents = 81920, 1, 32, 0                      # 40 MB, 80k clusters
    part = 2048
    nfats = 2
    # FAT size (entries * width over the data area), rounded up
    ent = 2 if fat_type == 16 else 4
    root_secs = rootents * 32 // SECTOR
    fatsz = 1
    while True:
        nclus = (total - rsv - nfats * fatsz - root_secs) // spc
        need = ((nclus + 2) * ent + SECTOR - 1) // SECTOR
        if need <= fatsz:
            break
        fatsz = need
    img = bytearray((part + total) * SECTOR)
    struct.pack_into("<B3xBBBxII", img, 0x1BE, 0x00, 0, 0, 0, 0, 0)
    img[0x1BE + 4] = 0x06 if fat_type == 16 else 0x0C
    struct.pack_into("<II", img, 0x1BE + 8, part, total)
    img[510:512] = b"\x55\xAA"
    b = part * SECTOR
    img[b:b + 3] = b"\xEB\x3C\x90"
    img[b + 3:b + 11] = b"AVKTEST "
    struct.pack_into("<HBHBHHBHHHII", img, b + 11, SECTOR, spc, rsv, nfats, rootents,
                     0, 0xF8, fatsz if fat_type == 16 else 0, 63, 255, part, total)
    if fat_type == 32:
        struct.pack_into("<IHHIHH", img, b + 36, fatsz, 0, 0, 2, 1, 6)
        img[b + 82:b + 90] = b"FAT32   "
    else:
        img[b + 54:b + 62] = b"FAT16   "
    img[b + 510:b + 512] = b"\x55\xAA"
    f = Fat(img)
    assert f.fat32 == (fat_type == 32), f.nclus

    def fat_set(n, v):
        for k in range(nfats):
            off = f.fat0 + k * fatsz * SECTOR
            if f.fat32:
                struct.pack_into("<I", img, off + 4 * n, v)
            else:
                struct.pack_into("<H", img, off + 2 * n, v)

    eoc = 0x0FFFFFFF if f.fat32 else 0xFFFF
    fat_set(0, 0x0FFFFFF8 if f.fat32 else 0xFFF8)
    fat_set(1, eoc)
    nxt = 2
    if f.fat32:
        fat_set(2, eoc)  # root directory: one cluster
        nxt = 3

    def alloc(n):
        nonlocal nxt
        out = []
        for _ in range(n):
            out.append(nxt)
            nxt += 2 if frag else 1   # --frag: a free cluster between the file's clusters
        return out

    entries = []
    for name, data in files.items():
        nc = (len(data) + f.csize - 1) // f.csize
        cl = alloc(nc)
        for i, c in enumerate(cl):
            fat_set(c, cl[i + 1] if i + 1 < len(cl) else eoc)
            o = f.clus_off(c)
            img[o:o + f.csize] = data[i * f.csize:(i + 1) * f.csize].ljust(f.csize, b"\0")
        if lfn:  # a long-name entry in front, which readers must skip
            entries.append(bytes([0x41]) + b"x\0" * 5 + bytes([0x0F, 0, 0]) + b"\xff" * 12 + b"\0\0" + b"\xff" * 4)
        e = bytearray(32)
        e[:11] = name83(name)
        e[11] = 0x20
        struct.pack_into("<H", e, 20, (cl[0] >> 16) if cl else 0)
        struct.pack_into("<H", e, 26, (cl[0] & 0xFFFF) if cl else 0)
        struct.pack_into("<I", e, 28, len(data))
        entries.append(bytes(e))
    vol = bytearray(32)
    vol[:11] = b"AVK6       "
    vol[11] = 0x08
    entries.insert(0, bytes(vol))
    offs = list(f.root_entries())
    assert len(entries) <= len(offs)
    for o, e in zip(offs, entries):
        assert len(e) == 32
        img[o:o + 32] = e
    with open(path, "wb") as fh:
        fh.write(img)


def main(argv):
    if argv[0] == "make":
        path, t = argv[1], int(argv[2])
        files = {}
        for a in argv[3:]:
            if "=" in a:
                n, p = a.split("=", 1)
                files[n] = open(p, "rb").read()
        make(path, t, files, frag="--frag" in argv, lfn="--lfn" in argv)
    elif argv[0] == "cat":
        sys.stdout.buffer.write(Fat(bytearray(open(argv[1], "rb").read())).read(argv[2]))
    elif argv[0] == "check":
        Fat(bytearray(open(argv[1], "rb").read())).check()
        print("ok")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
