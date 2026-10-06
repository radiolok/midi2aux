import math
import random

import cocotb
from cocotb.triggers import RisingEdge

import rtlrun
from synthmodel import pitch
from tbutil import start


@cocotb.test()
async def bit_exact_and_accuracy(dut):
    dut.in_valid.value = 0
    dut.pitch.value = 0
    await start(dut)
    rng = random.Random(3)
    ps = [0, 1, 63, 64, 0xFFFF, 0x10000, (1 << 21) - 1] + [rng.randrange(1 << 21) for _ in range(3000)]
    ps += [(25 << 16) | (i << 6) | 63 for i in range(1024)]  # every table entry, max interpolation
    got = []
    for p in ps + [0, 0, 0]:
        dut.pitch.value = p
        dut.in_valid.value = 1
        await RisingEdge(dut.clk)
        if dut.out_valid.value:
            got.append(int(dut.inc.value))
    dut.in_valid.value = 0
    for _ in range(4):
        await RisingEdge(dut.clk)
        if dut.out_valid.value:
            got.append(int(dut.inc.value))
    got = got[: len(ps)]
    assert len(got) == len(ps)
    for p, g in zip(ps, got):
        assert g == pitch.pitch2inc(p), f"pitch {p:#x}: rtl {g:#x} model {pitch.pitch2inc(p):#x}"
        oct_ = p >> 16
        if oct_ >= 20:  # audio range: error below 0.02 cent
            ideal = 2.0 ** (p / 65536)
            if ideal < 2**32:
                assert abs(1200 * math.log2(g / ideal)) < 0.02


def test_pitch2inc():
    rtlrun.run("pitch2inc", rtlrun.rtl("audio/pitch2inc.sv", "audio/exp2_rom.sv"), module=__name__)
