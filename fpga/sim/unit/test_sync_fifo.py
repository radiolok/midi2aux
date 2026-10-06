import random
from collections import deque

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge

import rtlrun
from tbutil import start

DEPTH = 8


@cocotb.test()
async def random_push_pop(dut):
    dut.wr_en.value = 0
    dut.rd_en.value = 0
    dut.clr_overflow.value = 0
    dut.wr_data.value = 0
    await start(dut)
    ref = deque()
    overflow = False
    for cyc in range(3000):
        await FallingEdge(dut.clk)
        # outputs before the edge
        assert int(dut.empty.value) == (len(ref) == 0)
        assert int(dut.full.value) == (len(ref) == DEPTH)
        assert int(dut.count.value) == len(ref)
        assert int(dut.overflow.value) == overflow
        if ref:
            assert int(dut.rd_data.value) == ref[0]
        bias = 0.7 if cyc % 600 < 300 else 0.3  # alternately fill up and drain
        wr = random.random() < bias
        rd = random.random() < 1 - bias
        clr = random.random() < 0.02
        data = random.randrange(1 << 12)
        dut.wr_en.value, dut.rd_en.value, dut.wr_data.value, dut.clr_overflow.value = wr, rd, data, clr
        await RisingEdge(dut.clk)
        full = len(ref) == DEPTH
        if rd and ref:
            ref.popleft()
        if wr and not full:
            ref.append(data)
        if wr and full:
            overflow = True
        elif clr:
            overflow = False


def test_sync_fifo():
    rtlrun.run("sync_fifo", rtlrun.rtl("common/sync_fifo.sv"), {"WIDTH": 12, "DEPTH": DEPTH}, module=__name__)
