import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

import rtlrun
from synthmodel import fixed


@cocotb.test()
async def scale_and_saturate(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    xs = [0, 1, -1, fixed.ONE, -fixed.ONE, 81920, 81921, -81920, -81921, (1 << 17) - 1, -(1 << 17)]
    xs += [random.randrange(-(1 << 17), 1 << 17) for _ in range(2000)]
    # 1 clk latency: y after the edge that sampled x
    for x in xs:
        dut.x.value = x
        await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
        assert dut.y.value.signed_integer == fixed.to_dac(x), x
    assert fixed.to_dac(fixed.ONE) == 104858  # 1.0 МЕ = 0.8 FS


def test_dac_scale():
    rtlrun.run("dac_scale", rtlrun.rtl("audio/dac_scale.sv"), module=__name__)
