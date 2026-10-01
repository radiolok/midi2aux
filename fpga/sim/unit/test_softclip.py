import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

import rtlrun
from synthmodel import softclip

LAT = 3


@cocotb.test()
async def matches_model(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    rng = random.Random(2)
    xs = [0, 65536, 65537, -65537, 81920, 200000, -200000, 524287, -524288]
    xs += [rng.randrange(-(1 << 19), 1 << 19) for _ in range(3000)]
    xs += [rng.randrange(60000, 140000) * rng.choice((1, -1)) for _ in range(3000)]
    got = []
    for x in xs + [0] * LAT:
        dut.x.value = x
        await RisingEdge(dut.clk)
        got.append(dut.y.value.signed_integer)
    got = got[LAT:]
    for x, y in zip(xs, got):
        assert y == softclip.softclip(x), f"x={x}: rtl {y} model {softclip.softclip(x)}"


def test_softclip():
    rtlrun.run("softclip", rtlrun.rtl("audio/softclip.sv", "audio/tanh_rom.sv"), {"IN_W": 20}, module=__name__)
