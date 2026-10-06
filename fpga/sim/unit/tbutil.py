"""Shared cocotb helpers."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge


async def start(dut, period_ns=10, rst_cycles=4):
    cocotb.start_soon(Clock(dut.clk, period_ns, units="ns").start())
    dut.rst.value = 1
    await ClockCycles(dut.clk, rst_cycles)
    dut.rst.value = 0
    await RisingEdge(dut.clk)


async def uart_send(dut, sig, byte, bit_cycles, stop_ok=True):
    """Drive one 8N1 frame on `sig`, bit_cycles clocks per bit."""
    bits = [0] + [(byte >> i) & 1 for i in range(8)] + [1 if stop_ok else 0]
    for b in bits:
        sig.value = b
        await ClockCycles(dut.clk, bit_cycles)
    sig.value = 1
