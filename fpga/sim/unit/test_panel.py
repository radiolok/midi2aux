"""Panel peripherals: MCP3208 poller, encoder decoder, ST7789 stream controller."""

import random

import cocotb
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

import rtlrun
from tbutil import start


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


def idle_bus(dut, *extra):
    for s in ("req", "we", "addr") + extra:
        getattr(dut, s).value = 0
    if hasattr(dut, "wdata"):
        dut.wdata.value = 0


# --------------------------------------------------------------------- MCP3208
async def mcp3208(dut, values, frames):
    """SPI slave model: samples MOSI on SCK rising edges, drives MISO after falling edges."""
    while True:
        await FallingEdge(dut.cs_n)
        bits_in, out, nbit = 0, None, 0
        dut.miso.value = 1
        while True:
            await RisingEdge(dut.sck)
            if dut.cs_n.value:
                break
            bits_in = (bits_in << 1) | int(dut.mosi.value)
            nbit += 1
            if nbit == 10:  # start, SGL, D2 D1 D0 received (frame bits 5..9)
                ch = bits_in & 7
                assert (bits_in >> 3) & 3 == 3, "start + single-ended expected"
                # null bit then B11..B0 on the following clocks
                out = [0, 0] + [(values[ch] >> (11 - i)) & 1 for i in range(12)]
            await FallingEdge(dut.sck)
            if out:
                dut.miso.value = out.pop(0)
            if nbit == 24:
                frames.append(ch)
                break


@cocotb.test()
async def pots_scan_and_smooth(dut):
    idle_bus(dut)
    dut.miso.value = 1
    await start(dut)
    values = [0, 4095, 1234, 2048, 1, 4000, 777, 3333]
    frames = []
    cocotb.start_soon(mcp3208(dut, values, frames))
    await ClockCycles(dut.clk, 8 * 24 * 8 * 3)  # a few scans
    assert frames[:8] == list(range(8))
    for ch, v in enumerate(values):
        assert await rd(dut, 8 + ch) == v
        assert abs(await rd(dut, ch) - v * 16) <= 16 * 8  # seeded by the first scan, no ramp from 0
    # change a value: the smoothed register converges to value << 4
    values[2] = 3000
    await ClockCycles(dut.clk, 8 * 24 * 8 * 110)
    assert abs(await rd(dut, 2) - 3000 * 16) <= 16
    assert await rd(dut, 16) > 50


def test_periph_pots():
    rtlrun.run("periph_pots", rtlrun.rtl("panel/periph_pots.sv"),
               {"SYS_CLK_HZ": 8_000_000, "SPI_HZ": 1_000_000, "SMOOTH": 3}, module=__name__,
               testcase="pots_scan_and_smooth")


# -------------------------------------------------------------------- encoders
async def turn(dut, k, steps, bounce=True, dwell=60):
    """Drive encoder k by `steps` detents (4 quadrature transitions each), active-low signals."""
    seq = [(0, 0), (1, 0), (1, 1), (0, 1)] if steps > 0 else [(0, 0), (0, 1), (1, 1), (1, 0)]
    a, b = int(dut.enc_a.value), int(dut.enc_b.value)
    for _ in range(abs(steps)):
        for qa, qb in seq[1:] + seq[:1]:
            na = (a & ~(1 << k)) | ((1 - qa) << k)
            nb = (b & ~(1 << k)) | ((1 - qb) << k)
            if bounce:  # contact bounce shorter than the debounce time
                for _ in range(3):
                    dut.enc_a.value, dut.enc_b.value = na ^ (a ^ na), nb ^ (b ^ nb)
                    await ClockCycles(dut.clk, 2)
                    dut.enc_a.value, dut.enc_b.value = na, nb
                    await ClockCycles(dut.clk, 2)
            a, b = na, nb
            dut.enc_a.value, dut.enc_b.value = a, b
            await ClockCycles(dut.clk, dwell)


@cocotb.test()
async def encoders_count_and_buttons(dut):
    idle_bus(dut)
    dut.enc_a.value = 0xF  # released (active low)
    dut.enc_b.value = 0xF
    dut.enc_sw.value = 0xF
    await start(dut)
    await ClockCycles(dut.clk, 50)
    await turn(dut, 0, 3)
    await turn(dut, 2, -2)
    await turn(dut, 0, -1, bounce=False)
    assert (await rd(dut, 0)) == 2
    assert (await rd(dut, 2)) == (-2) & 0xFFFFFFFF
    assert (await rd(dut, 1)) == 0
    await wr(dut, 0, 0)
    assert (await rd(dut, 0)) == 0
    # button 1: press with bounce, hold, release
    for _ in range(4):
        dut.enc_sw.value = 0xD
        await ClockCycles(dut.clk, 3)
        dut.enc_sw.value = 0xF
        await ClockCycles(dut.clk, 3)
    dut.enc_sw.value = 0xD
    await ClockCycles(dut.clk, 60)
    assert (await rd(dut, 4)) == 0b0010
    dut.enc_sw.value = 0xF
    await ClockCycles(dut.clk, 60)
    assert (await rd(dut, 4)) == 0
    assert (await rd(dut, 5)) == 0b0010  # one press event despite the bounce
    await wr(dut, 5, 0b0010)
    assert (await rd(dut, 5)) == 0


def test_periph_enc():
    rtlrun.run("periph_enc", rtlrun.rtl("panel/periph_enc.sv"),
               {"SYS_CLK_HZ": 1_000_000, "N": 4, "DEBOUNCE_US": 20, "STEPS": 4}, module=__name__,
               testcase="encoders_count_and_buttons")


# ------------------------------------------------------------------------ LCD
async def spi_monitor(dut, out):
    """Collect (dc, byte) from the LCD SPI stream (mode 0, MSB first)."""
    while True:
        await FallingEdge(dut.cs_n)
        byte, n = 0, 0
        while True:
            await RisingEdge(dut.sck)
            byte = (byte << 1) | int(dut.mosi.value)
            n += 1
            if n == 8:
                out.append((int(dut.dc.value), byte))
                byte, n = 0, 0
            if dut.cs_n.value:
                break


async def wait_idle(dut):
    while (await rd(dut, 1)) >> 31:
        await ClockCycles(dut.clk, 20)
    await ClockCycles(dut.clk, 40)


@cocotb.test()
async def lcd_stream(dut):
    idle_bus(dut)
    await start(dut)
    got = []
    cocotb.start_soon(spi_monitor(dut, got))
    await wr(dut, 3, 0xF800)  # FG red
    await wr(dut, 4, 0x001F)  # BG blue
    await wr(dut, 2, 0b11)
    await RisingEdge(dut.clk)
    assert dut.rst_n.value == 1 and dut.bl.value == 1
    await wr(dut, 0, 0x2C)                      # command RAMWR
    await wr(dut, 0, 0x100 | 0xA5)              # data byte
    await wr(dut, 0, (1 << 30) | 3)             # fill 3 pixels FG
    await wr(dut, 0, (2 << 30) | (4 << 16) | 0b1010000000000000)  # 5 bits: 1 0 1 0 0
    await wait_idle(dut)
    red, blue = [(1, 0xF8), (1, 0x00)], [(1, 0x00), (1, 0x1F)]
    expect = [(0, 0x2C), (1, 0xA5)] + red * 3 + red + blue + red + blue + blue
    assert got == expect, got
    # colours changed inside the stream apply in order
    got.clear()
    await wr(dut, 0, (3 << 30) | 0x07E0)             # FG green
    await wr(dut, 0, (3 << 30) | (1 << 16) | 0xFFFF)  # BG white
    await wr(dut, 0, (2 << 30) | (1 << 16) | 0x8000)  # 2 bits: 1 0
    await wr(dut, 0, (3 << 30) | 0x0001)
    await wr(dut, 0, (1 << 30) | 1)
    await wait_idle(dut)
    assert got == [(1, 0x07), (1, 0xE0), (1, 0xFF), (1, 0xFF), (1, 0x00), (1, 0x01)], got
    # a long random stream keeps order under FIFO back-pressure
    got.clear()
    rng = random.Random(1)
    ref = []
    for _ in range(200):
        b = rng.randrange(512)
        while (await rd(dut, 1)) >> 30 & 1:
            await ClockCycles(dut.clk, 10)
        await wr(dut, 0, b)
        ref.append((b >> 8, b & 0xFF))
    await wait_idle(dut)
    assert got == ref


def test_lcd_ctrl():
    rtlrun.run("lcd_ctrl", rtlrun.rtl("panel/lcd_ctrl.sv", "common/sync_fifo.sv"),
               {"FIFO_DEPTH": 16, "DIV_RST": 1}, module=__name__, testcase="lcd_stream")
