"""AVK inputs: AD7091R front end + FIR decimator (vs synthmodel.avk), SYNC input."""

import random

import cocotb
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

import rtlrun
from synthmodel import avk
from tbutil import start

PERIOD = 512


async def wr(dut, addr, val):
    dut.req.value, dut.we.value, dut.addr.value, dut.wdata.value = 1, 1, addr, val & 0xFFFFFFFF
    await RisingEdge(dut.clk)
    dut.req.value, dut.we.value = 0, 0


async def rd(dut, addr):
    dut.req.value, dut.we.value, dut.addr.value = 1, 0, addr
    await RisingEdge(dut.clk)
    dut.req.value = 0
    await RisingEdge(dut.clk)
    return int(dut.rdata.value)


async def ad7091r(dut, codes1, codes2, taken):
    """Two ADCs: a conversion samples the next code; MSB on CS fall, next bits after SCLK falls."""
    while True:
        await FallingEdge(dut.convst_n)
        c1, c2 = codes1.pop(0), codes2.pop(0)
        taken.append((c1, c2))
        await FallingEdge(dut.cs_n)
        for bit in range(11, -1, -1):
            dut.sdo1.value = (c1 >> bit) & 1
            dut.sdo2.value = (c2 >> bit) & 1
            await FallingEdge(dut.sclk)


@cocotb.test()
async def adc_decimation(dut):
    for sgn in ("tick", "req", "we", "addr", "wdata", "sdo1", "sdo2"):
        getattr(dut, sgn).value = 0
    await start(dut)
    rng = random.Random(4)
    n_out = 200
    codes1 = [rng.randrange(4096) for _ in range(4 * n_out + 8)]
    codes2 = [2048 + int(1500 * ((i // 7) % 2 * 2 - 1)) for i in range(4 * n_out + 8)]  # square wave
    taken = []
    cocotb.start_soon(ad7091r(dut, list(codes1), list(codes2), taken))
    await wr(dut, 2, 2000)          # OFFSET2
    await wr(dut, 3, 41 << 16)      # GAIN2
    d1, d2 = avk.Decimator(), avk.Decimator()
    got, ref = [], []
    for n in range(n_out):
        dut.tick.value = 1
        await RisingEdge(dut.clk)
        dut.tick.value = 0
        # mid-period: the output from the previous period's 4 conversions is there
        await ClockCycles(dut.clk, PERIOD // 2)
        got.append((dut.in1.value.signed_integer, dut.in2.value.signed_integer))
        await ClockCycles(dut.clk, PERIOD // 2 - 1)
    # model: every group of 4 conversions (one sample period) gives one output
    for i, (c1, c2) in enumerate(taken[: 4 * (n_out - 1)]):
        y1 = d1.push(avk.adc_to_q16(c1))
        y2 = d2.push(avk.adc_to_q16(c2, 2000, 41 << 16))
        if y1 is not None:
            ref.append((y1, y2))
    # the output for the conversions of period n is visible during period n + 1 (latency 1 sample)
    assert got[0] == (0, 0)
    assert got[1:len(ref) + 1] == ref
    assert await rd(dut, 4) == taken[-1][0]  # RAW1: the last code
    assert await rd(dut, 8) >= n_out - 1      # COUNT


def test_adc_in():
    rtlrun.run("adc_in", rtlrun.rtl("avk/adc_in.sv", "avk/fir_rom.sv"),
               {"PERIOD": PERIOD, "CONV_CYC": 10, "SCLK_HALF": 2}, module=__name__, testcase="adc_decimation")


# --------------------------------------------------------------------- SYNC
@cocotb.test()
async def sync_edges_period_filter(dut):
    for sgn in ("tick", "req", "we", "addr", "wdata", "sync_pin"):
        getattr(dut, sgn).value = 0
    await start(dut)
    await wr(dut, 3, 10)  # glitch filter: 10 clk
    edge_ticks = []

    async def ticker():
        while True:
            dut.tick.value = 1
            await RisingEdge(dut.clk)
            dut.tick.value = 0
            await ClockCycles(dut.clk, 99)
            edge_ticks.append(int(dut.edge_tick.value))

    cocotb.start_soon(ticker())
    for _ in range(5):  # square wave, period 1000 clk, with glitches in the low half
        dut.sync_pin.value = 1
        await ClockCycles(dut.clk, 500)
        dut.sync_pin.value = 0
        await ClockCycles(dut.clk, 200)
        for _ in range(3):  # 4-clk glitches: filtered out
            dut.sync_pin.value = 1
            await ClockCycles(dut.clk, 4)
            dut.sync_pin.value = 0
            await ClockCycles(dut.clk, 20)
        await ClockCycles(dut.clk, 300 - 72)
    assert await rd(dut, 2) == 5              # EDGES (word addresses)
    assert await rd(dut, 1) == 1000           # PERIOD
    assert sum(edge_ticks) == 5               # one flag per edge
    assert dut.level.value == 0


def test_sync_in():
    rtlrun.run("sync_in", rtlrun.rtl("avk/sync_in.sv"), module=__name__, testcase="sync_edges_period_filter")
