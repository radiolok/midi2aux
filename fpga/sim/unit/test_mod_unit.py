"""mod_unit RTL vs synthmodel.modunit, bit-exact."""

import random

import cocotb
from cocotb.triggers import ClockCycles, RisingEdge

import rtlrun
from synthmodel import modunit
from synthmodel.modunit import ModUnit, Route
from tbutil import start

FS = 48339.84


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


async def configure(dut, m, rng):
    for i in range(2):
        l = m.lfo[i]
        l.inc = rng.choice([rng.randrange(1 << 22), rng.randrange(1 << 28), 0])
        l.wave = rng.randrange(6)
        l.sync_reset = rng.randrange(2)
        await wr(dut, 8 * i, l.inc)
        await wr(dut, 8 * i + 4, l.sync_reset << 4 | l.wave)
    m.modwheel = rng.randrange(1 << 17)
    m.am_base = rng.choice([0, 1 << 16, rng.randrange(-(1 << 17), 1 << 17)])
    m.aux = rng.randrange(-(1 << 17), 1 << 17)
    await wr(dut, 0x10, m.modwheel)
    await wr(dut, 0x14, m.am_base)
    await wr(dut, 0x18, m.aux)
    m.follow_src, m.follow_atk, m.follow_rel = rng.randrange(2), rng.randrange(1 << 16), rng.randrange(1 << 16)
    for addr, v in ((0x20, m.follow_src), (0x24, m.follow_atk), (0x28, m.follow_rel)):
        await wr(dut, addr, v)
    for k in range(8):
        r = Route(rng.randrange(12), rng.choice([0, 0, rng.randrange(12)]), rng.randrange(5),
                  rng.randrange(-(1 << 23), 1 << 23))
        m.routes[k] = r
        await wr(dut, 0x40 + 8 * k, r.dst << 8 | r.via << 4 | r.src)
        await wr(dut, 0x44 + 8 * k, r.depth)


@cocotb.test()
async def bit_exact_random(dut):
    rng = random.Random(4)
    for sig in ("tick", "req", "we", "addr", "wdata", "in1", "in2", "sync", "sync_edge", "env"):
        getattr(dut, sig).value = 0
    await start(dut)
    m = ModUnit()
    for scene in range(6):
        await configure(dut, m, rng)
        gate = rng.randrange(2)
        m_gate = gate
        await wr(dut, 0x1C, gate)
        for n in range(400):
            i1, i2 = rng.randrange(-(1 << 17), 1 << 17), rng.choice([rng.randrange(-(1 << 17), 1 << 17), -(1 << 17)])
            if scene % 2:  # slowly varying inputs: the follower tracks them
                i1, i2 = (n * 331) % (1 << 17) - (1 << 16), -((n * 97) % (1 << 17))
            env, sy = rng.randrange(1 << 16), rng.randrange(2)
            se = int(rng.random() < 0.01)
            dut.in1.value, dut.in2.value, dut.env.value, dut.sync.value, dut.sync_edge.value = i1, i2, env, sy, se
            dut.tick.value = 1
            await RisingEdge(dut.clk)
            dut.tick.value = 0
            dut.sync_edge.value = 0
            await ClockCycles(dut.clk, 40)
            ref = m.step(in1=i1, in2=i2, sync=sy, sync_edge=se, env=env, gate=m_gate)
            got = (dut.pm.value.signed_integer, dut.cm.value.signed_integer, dut.am.value.signed_integer,
                   dut.pw.value.signed_integer)
            assert got == ref, f"scene {scene} sample {n}: rtl {got} model {ref}"
            assert dut.lfo1.value.signed_integer == m.lfo_out[0]
            assert dut.lfo2.value.signed_integer == m.lfo_out[1]
    assert await rd(dut, 0x80) == m.lfo_out[0]
    assert await rd(dut, 0x88) == m.follow


def test_mod_unit():
    rtlrun.run("mod_unit", rtlrun.rtl("voice/mod_unit.sv"), module=__name__)
