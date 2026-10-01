import random

import cocotb
from cocotb.triggers import ClockCycles, RisingEdge

import rtlrun
from synthmodel import midi
from tbutil import start


def random_stream(n, rng):
    out = []
    while len(out) < n:
        r = rng.random()
        if r < 0.45:
            st = rng.choice([0x80, 0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0]) | rng.randrange(16)
            out.append(st)
            for _ in range(midi.data_len(st)):
                out.append(rng.choice([0, rng.randrange(128)]))
        elif r < 0.65:  # running status data
            out += [rng.randrange(128) for _ in range(rng.choice([1, 2, 2, 4]))]
        elif r < 0.8:  # realtime anywhere
            out.append(rng.choice([0xF8, 0xFA, 0xFB, 0xFC, 0xFE, 0xFF]))
        elif r < 0.88:  # sysex
            out += [0xF0] + [rng.randrange(128) for _ in range(rng.randrange(6))] + [0xF7]
        else:  # system common with data
            st = rng.choice([0xF1, 0xF2, 0xF3, 0xF6])
            out += [st] + [rng.randrange(128) for _ in range({0xF1: 1, 0xF2: 2, 0xF3: 1, 0xF6: 0}[st])]
    return out


async def collect(dut, out):
    while True:
        await RisingEdge(dut.clk)
        if dut.ev_valid.value:
            out.append((int(dut.ev_status.value), int(dut.ev_d1.value), int(dut.ev_d2.value)))


async def feed(dut, stream):
    for b in stream:
        dut.in_data.value = b
        dut.in_valid.value = 1
        await RisingEdge(dut.clk)
        dut.in_valid.value = 0
        await ClockCycles(dut.clk, random.randrange(0, 3))
    await ClockCycles(dut.clk, 4)


@cocotb.test()
async def known_sequences(dut):
    dut.in_valid.value = 0
    await start(dut)
    got = []
    cocotb.start_soon(collect(dut, got))
    stream = [0x45, 0x90, 0x45, 0x64, 0x48, 0xF8, 0x50, 0x48, 0x00, 0xC3, 0x05, 0x06,
              0xF0, 0x01, 0x02, 0xF7, 0x40, 0x40, 0xB0, 0x7B, 0x00, 0xFC]
    await feed(dut, stream)
    assert got == [(0x90, 0x45, 0x64), (0xF8, 0, 0), (0x90, 0x48, 0x50), (0x80, 0x48, 0x40),
                   (0xC3, 0x05, 0), (0xC3, 0x06, 0), (0xB0, 0x7B, 0x00), (0xFC, 0, 0)]
    assert got == midi.parse(stream)


@cocotb.test()
async def random_vs_model(dut):
    dut.in_valid.value = 0
    await start(dut)
    got = []
    cocotb.start_soon(collect(dut, got))
    stream = random_stream(3000, random.Random(7))
    await feed(dut, stream)
    assert got == midi.parse(stream)


def test_midi_parser():
    rtlrun.run("midi_parser", rtlrun.rtl("midi/midi_parser.sv"), module=__name__)
