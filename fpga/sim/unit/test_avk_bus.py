"""Slot MATH and the signal bus / mixer vs synthmodel.avk, bit-exact."""

import random

import cocotb
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

import rtlrun
from synthmodel import avk
from tbutil import start

ONE = 1 << 16


def rnd18(rng):
    return rng.choice([0, ONE, -ONE, (1 << 17) - 1, -(1 << 17), rng.randrange(-(1 << 17), 1 << 17),
                       rng.randrange(-4096, 4096)])


# ---------------------------------------------------------------- slot MATH
@cocotb.test()
async def math_ops_random(dut):
    dut.start.value = 0
    dut.p_we.value = 0
    dut.a.value = dut.b.value = 0
    await start(dut)
    rng = random.Random(8)
    for n in range(3000):
        op = rng.randrange(10)  # 9 = unknown: passes A
        k = rnd18(rng)
        for addr, val in ((0, op), (1, k)):
            dut.p_we.value, dut.p_addr.value, dut.p_wdata.value = 1, addr, val & 0xFFFFFFFF
            await RisingEdge(dut.clk)
        dut.p_we.value = 0
        a, b = rnd18(rng), rnd18(rng)
        dut.a.value, dut.b.value, dut.start.value = a, b, 1
        await RisingEdge(dut.clk)
        dut.start.value = 0
        for _ in range(60):
            await RisingEdge(dut.clk)
            if dut.done.value:
                break
        else:
            raise AssertionError("no done")
        ref = avk.math_op(op, a, b, k)
        assert dut.y.value.signed_integer == ref, f"op {op} a {a} b {b} k {k}: rtl {dut.y.value.signed_integer} model {ref}"


def test_slot_math():
    rtlrun.run("slot_math", rtlrun.rtl("avk/slot_math.sv"), module=__name__, testcase="math_ops_random")


# --------------------------------------------------------------------- bus
async def wr(dut, addr, val):
    dut.req.value, dut.we.value, dut.addr.value, dut.wdata.value = 1, 1, addr, val & 0xFFFFFFFF
    await RisingEdge(dut.clk)
    dut.req.value, dut.we.value = 0, 0


async def rd(dut, addr):
    dut.req.value, dut.we.value, dut.addr.value = 1, 0, addr
    await RisingEdge(dut.clk)
    dut.req.value = 0
    await RisingEdge(dut.clk)
    return dut.rdata.value.signed_integer


@cocotb.test()
async def bus_random(dut):
    for sig in ("tick", "req", "we", "addr", "wdata", "synth", "in1", "in2", "lfo1", "lfo2", "sync", "env", "gate"):
        getattr(dut, sig).value = 0
    await start(dut)
    rng = random.Random(3)
    m = avk.AvkBus((avk.TYPE_MATH,) * 3)
    for scene in range(8):
        # configuration
        for i in range(m.n):
            m.gain[i] = rng.choice([0, 0, ONE, rng.randrange(-(1 << 17), 1 << 17)])
            await wr(dut, 0x40 + 4 * i, m.gain[i])
        m.out_dc, m.out2_dc = rng.randrange(-8000, 8000), rng.randrange(-8000, 8000)
        m.sel2, m.gain2 = rng.randrange(m.n), rnd18(rng)
        for addr, val in ((0, m.out_dc), (4, m.out2_dc), (8, m.sel2), (12, m.gain2)):
            await wr(dut, addr, val)
        for k, sl in enumerate(m.slots):
            sl.sel_a, sl.sel_b, sl.bypass = rng.randrange(m.n), rng.randrange(m.n), int(rng.random() < 0.2)
            sl.param[0], sl.param[1] = rng.randrange(9), rnd18(rng)
            base = 0x10000 + 0x100 * k
            for addr, val in ((4, sl.sel_a), (8, sl.sel_b), (12, sl.bypass), (0x40, sl.param[0]), (0x44, sl.param[1])):
                await wr(dut, base + addr, val)
        for n in range(40):
            ins = [rnd18(rng) for _ in range(5)] + [rng.randrange(2), rnd18(rng), rng.randrange(2)]
            for sig, v in zip(("synth", "in1", "in2", "lfo1", "lfo2", "sync", "env", "gate"), ins):
                getattr(dut, sig).value = v
            dut.tick.value = 1
            await RisingEdge(dut.clk)
            dut.tick.value = 0
            await ClockCycles(dut.clk, 200)
            ref = m.sample(*ins)
            got = (dut.out.value.signed_integer, dut.out2.value.signed_integer)
            assert got == ref, f"scene {scene} sample {n}: rtl {got} model {ref}"
        for i in range(m.n):  # bus read-back
            assert await rd(dut, 0x100 + 4 * i) == m.s[i]
    assert await rd(dut, 0x10000) == avk.TYPE_MATH


async def memory(dut, mem, rng, max_lat=6):
    """External memory behind the port: random latency, one-cycle ack (mem/mem_arb.sv protocol).
    Samples and drives on falling edges, so it sees settled values."""
    dut.m_ack.value = 0
    while True:
        await FallingEdge(dut.clk)
        dut.m_ack.value = 0
        if not dut.m_req.value:
            continue
        for _ in range(rng.randrange(max_lat)):
            await FallingEdge(dut.clk)
        a = int(dut.m_addr.value)
        if dut.m_we.value:
            mem[a] = int(dut.m_wdata.value)
        dut.m_rdata.value = mem[a]
        dut.m_ack.value = 1


@cocotb.test()
async def bus_delay(dut):
    """Slots MATH, DELAY, DELAY sharing one memory; delay lines in two regions."""
    for sig in ("tick", "req", "we", "addr", "wdata", "synth", "in1", "in2", "lfo1", "lfo2", "sync", "env", "gate",
                "m_ack", "m_rdata"):
        getattr(dut, sig).value = 0
    words = 64
    m = avk.AvkBus((avk.TYPE_MATH, avk.TYPE_DELAY, avk.TYPE_DELAY), mem_words=words)
    rng = random.Random(5)
    await start(dut)
    cocotb.start_soon(memory(dut, [0] * words, rng))  # the RTL memory, separate from the model
    for i in range(m.n):
        m.gain[i] = rng.randrange(-(1 << 16), 1 << 16)
        await wr(dut, 0x40 + 4 * i, m.gain[i])
    for scene in range(6):
        for k in (1, 2):
            sl = m.slots[k]
            sl.sel_a, sl.bypass = rng.choice([avk.S_IN1, avk.S_IN2, 8]), int(rng.random() < 0.15)
            sl.mem_base = (k - 1) * 32
            sl.mem_size = rng.choice([0, 1, 5, 17, 32]) if scene else 32
            sl.param[:4] = [rng.randrange(40), rnd18(rng), rnd18(rng), rnd18(rng)]
            base = 0x10000 + 0x100 * k
            regs = [(4, sl.sel_a), (12, sl.bypass), (0x10, sl.mem_base), (0x14, sl.mem_size)]
            regs += [(0x40 + 4 * j, v) for j, v in enumerate(sl.param[:4])]
            for addr, val in regs:
                await wr(dut, base + addr, val)
        for n in range(60):
            ins = [rnd18(rng) for _ in range(5)] + [rng.randrange(2), rnd18(rng), rng.randrange(2)]
            for sig, v in zip(("synth", "in1", "in2", "lfo1", "lfo2", "sync", "env", "gate"), ins):
                getattr(dut, sig).value = v
            dut.tick.value = 1
            await RisingEdge(dut.clk)
            dut.tick.value = 0
            await ClockCycles(dut.clk, 300)
            ref = m.sample(*ins)
            got = (dut.out.value.signed_integer, dut.out2.value.signed_integer)
            if got != ref:
                bus = [await rd(dut, 0x100 + 4 * i) for i in range(m.n)]
                cfg = [(sl.sel_a, sl.bypass, sl.mem_size, sl.param[:4], sl.wp) for sl in m.slots[1:]]
                raise AssertionError(f"scene {scene} sample {n}: rtl {got} model {ref}\nbus {bus}\nref {m.s}\n{cfg}")
    assert await rd(dut, 0x10000 + 0x200) == avk.TYPE_DELAY


def test_fx_bus_delay():
    rtlrun.run("fx_bus", rtlrun.rtl("avk/fx_bus.sv", "avk/slot_math.sv", "avk/slot_delay.sv", "avk/slot_chorus.sv",
                                    "avk/slot_reverb.sv", "audio/softclip.sv",
                                    "audio/tanh_rom.sv"),
               {"NUM_SLOTS": 3, "SLOT_TYPES": 0x020201}, module=__name__, testcase="bus_delay")


def test_fx_bus():
    rtlrun.run("fx_bus", rtlrun.rtl("avk/fx_bus.sv", "avk/slot_math.sv", "avk/slot_delay.sv", "avk/slot_chorus.sv",
                                    "avk/slot_reverb.sv", "audio/softclip.sv",
                                    "audio/tanh_rom.sv"),
               {"NUM_SLOTS": 3, "SLOT_TYPES": 0x010101}, module=__name__, testcase="bus_random")


@cocotb.test()
async def bus_chorus_reverb(dut):
    """Slots CHORUS, REVERB, MATH: random parameters, inputs and memory latency."""
    for sig in ("tick", "req", "we", "addr", "wdata", "synth", "in1", "in2", "lfo1", "lfo2", "sync", "env", "gate",
                "m_ack", "m_rdata"):
        getattr(dut, sig).value = 0
    words = 64 + 5934
    m = avk.AvkBus((avk.TYPE_CHORUS, avk.TYPE_REVERB, avk.TYPE_MATH), mem_words=words)
    rng = random.Random(11)
    await start(dut)
    cocotb.start_soon(memory(dut, [0] * words, rng))
    for i in range(m.n):
        m.gain[i] = rng.randrange(-(1 << 16), 1 << 16)
        await wr(dut, 0x40 + 4 * i, m.gain[i])
    for scene in range(5):
        ch, rv = m.slots[0], m.slots[1]
        ch.mem_base, ch.mem_size = 0, rng.choice([0, 2, 3, 40, 64]) if scene else 64
        rv.mem_base, rv.mem_size = 64, rng.choice([100, 5934]) if scene else 5934
        ch.param[:6] = [rng.randrange(50), rng.randrange(70), rng.getrandbits(32), rnd18(rng), rnd18(rng), rnd18(rng)]
        rv.param[:4] = [rng.randrange(1 << 16), rng.randrange(1 << 16), rnd18(rng), rnd18(rng)]
        for k, sl in ((0, ch), (1, rv)):
            sl.sel_a, sl.bypass = rng.choice([avk.S_IN1, avk.S_IN2, 10]), int(rng.random() < 0.15)
            base = 0x10000 + 0x100 * k
            regs = [(4, sl.sel_a), (12, sl.bypass), (0x10, sl.mem_base), (0x14, sl.mem_size)]
            regs += [(0x40 + 4 * j, v) for j, v in enumerate(sl.param[:6])]
            for addr, val in regs:
                await wr(dut, base + addr, val)
        for n in range(150):
            ins = [rnd18(rng) for _ in range(5)] + [rng.randrange(2), rnd18(rng), rng.randrange(2)]
            for sig, v in zip(("synth", "in1", "in2", "lfo1", "lfo2", "sync", "env", "gate"), ins):
                getattr(dut, sig).value = v
            dut.tick.value = 1
            await RisingEdge(dut.clk)
            dut.tick.value = 0
            await ClockCycles(dut.clk, 500)
            ref = m.sample(*ins)
            got = (dut.out.value.signed_integer, dut.out2.value.signed_integer)
            assert got == ref, f"scene {scene} sample {n}: rtl {got} model {ref}"
    assert await rd(dut, 0x10000) == avk.TYPE_CHORUS
    assert await rd(dut, 0x10100) == avk.TYPE_REVERB


def test_fx_bus_chorus_reverb():
    rtlrun.run("fx_bus", rtlrun.rtl("avk/fx_bus.sv", "avk/slot_math.sv", "avk/slot_delay.sv", "avk/slot_chorus.sv",
                                    "avk/slot_reverb.sv", "audio/softclip.sv", "audio/tanh_rom.sv"),
               {"NUM_SLOTS": 3, "SLOT_TYPES": 0x010403}, module=__name__, testcase="bus_chorus_reverb")
