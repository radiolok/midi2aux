import random

import cocotb
from cocotb.triggers import ClockCycles, RisingEdge

import rtlrun
from tbutil import start, uart_send

SYS, BAUD = 3_200_000, 100_000  # 32 clk per bit
BIT = 32


async def collect(dut, out):
    while True:
        await RisingEdge(dut.clk)
        if dut.valid.value:
            out.append(int(dut.data.value))


@cocotb.test()
async def bytes_roundtrip(dut):
    dut.rx.value = 1
    await start(dut)
    got = []
    cocotb.start_soon(collect(dut, got))
    data = [0x00, 0xFF, 0x55, 0xAA, 0x90] + [random.randrange(256) for _ in range(40)]
    for b in data:
        # +-3 % baud mismatch must be tolerated
        await uart_send(dut, dut.rx, b, BIT + random.choice((-1, 0, 1)))
        await ClockCycles(dut.clk, random.randrange(0, 20))
    await ClockCycles(dut.clk, 80)
    assert got == data


@cocotb.test()
async def framing_error_dropped(dut):
    dut.rx.value = 1
    await start(dut)
    got = []
    cocotb.start_soon(collect(dut, got))
    await uart_send(dut, dut.rx, 0x3C, BIT, stop_ok=False)
    await ClockCycles(dut.clk, 80)
    await uart_send(dut, dut.rx, 0xC3, BIT)
    await ClockCycles(dut.clk, 80)
    assert got == [0xC3]


@cocotb.test()
async def glitch_ignored(dut):
    dut.rx.value = 1
    await start(dut)
    got = []
    cocotb.start_soon(collect(dut, got))
    dut.rx.value = 0
    await ClockCycles(dut.clk, 6)  # shorter than half a bit
    dut.rx.value = 1
    await ClockCycles(dut.clk, 120)
    assert got == []


def test_uart_rx():
    rtlrun.run("uart_rx", rtlrun.rtl("midi/uart_rx.sv"), {"SYS_CLK_HZ": SYS, "BAUD": BAUD}, module=__name__)
