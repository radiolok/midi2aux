"""voice_engine RTL vs synthmodel.voice, bit-exact, random parameters and gates."""

import random

import cocotb
from cocotb.triggers import ClockCycles, RisingEdge

import rtlrun
from synthmodel import voice
from synthmodel.voice import VoiceEngine
from tbutil import start

NV = 4
FS = 48339.84
GLOBAL_REGS = {"waves": 0, "pw": 1, "g1": 2, "g2": 3, "gn": 4, "cutoff": 5, "env2_depth": 6, "res_q": 7,
               "fmode": 8, "master": 9, "a1": 10, "d1": 11, "s1": 12, "r1": 13, "a2": 14, "d2": 15,
               "s2": 16, "r2": 17, "pm": 18, "cm": 19, "am": 20, "hsync": 23}
VOICE_REGS = {"pitch1": 0, "pitch2": 1, "gate": 2, "vel_amp": 3, "cut_ofs": 4}


class Bus:
    def __init__(self, dut):
        self.dut = dut

    async def write(self, addr, data):
        d = self.dut
        d.req.value, d.we.value, d.addr.value, d.wdata.value = 1, 1, addr, data & 0xFFFFFFFF
        await RisingEdge(d.clk)
        d.req.value, d.we.value = 0, 0

    async def read(self, addr):
        d = self.dut
        d.req.value, d.we.value, d.addr.value = 1, 0, addr
        await RisingEdge(d.clk)
        d.req.value = 0
        await RisingEdge(d.clk)
        return int(d.rdata.value)

    async def glob(self, name, val):
        await self.write((1 << 16) | (GLOBAL_REGS[name] << 2), val)

    async def vreg(self, v, name, val):
        await self.write((v << 6) | (VOICE_REGS[name] << 2), val)


class Harness:
    def __init__(self, dut, rng):
        self.dut, self.bus, self.rng = dut, Bus(dut), rng
        self.m = VoiceEngine(NV)
        self.am_reg = 1 << 16
        self.am_ext = 1 << 16

    async def set_glob(self, name, val):
        g = self.m.g
        if name == "waves":
            g.wave1, g.wave2 = val & 3, (val >> 2) & 3
        elif name in ("a1", "d1", "s1", "r1", "a2", "d2", "s2", "r2"):
            env = g.env1 if name[1] == "1" else g.env2
            setattr(env, name[0], val)
        elif name == "am":
            self.am_reg = val
        else:
            setattr(g, name, val)
        g.am = voice.sat((self.am_reg * self.am_ext) >> 16, 18)
        await self.bus.glob(name, val)

    async def set_voice(self, v, name, val):
        r = self.m.regs[v]
        if name == "gate":
            r.gate, r.retrig = val & 1, (val >> 1) & 1
        else:
            setattr(r, name, val)
        await self.bus.vreg(v, name, val)

    async def sample(self, sync_edge=0):
        """One tick; returns (rtl, model) S0."""
        d = self.dut
        d.sync_edge.value = sync_edge
        d.tick.value = 1
        await RisingEdge(d.clk)
        d.tick.value = 0
        while True:
            await RisingEdge(d.clk)
            if d.s0_valid.value:
                break
        return d.s0.value.signed_integer, self.m.sample(sync_edge)


def rand_env(rng):
    sus = rng.choice([0.0, 1.0, rng.random(), rng.random()])  # 0 and 1 are corner cases
    return voice.env_params(rng.uniform(0.001, 0.01), rng.uniform(0.002, 0.03), sus,
                            rng.uniform(0.002, 0.02), FS)


async def setup(dut):
    dut.tick.value = 0
    dut.req.value = 0
    dut.we.value = 0
    dut.addr.value = 0
    dut.wdata.value = 0
    dut.pm_ext.value = 0
    dut.cm_ext.value = 0
    dut.am_ext.value = 1 << 16
    dut.pw_ext.value = 0
    dut.sync_edge.value = 0
    await start(dut)
    await ClockCycles(dut.clk, NV + 2)  # clear pass after reset


async def randomize(h, rng):
    await h.set_glob("waves", rng.randrange(16))
    await h.set_glob("pw", rng.randrange(1 << 16))
    for g in ("g1", "g2", "gn"):
        await h.set_glob(g, rng.choice([0, rng.randrange(1 << 16), 1 << 16]))
    await h.set_glob("cutoff", rng.randrange(1_000_000, voice.C_MAX + 1))
    await h.set_glob("env2_depth", rng.randrange(-(1 << 19), 1 << 19))
    await h.set_glob("res_q", rng.choice([0, rng.randrange(1 << 17), 1 << 16]))
    await h.set_glob("fmode", rng.randrange(4))
    await h.set_glob("master", rng.randrange(1 << 17))
    e1, e2 = rand_env(rng), rand_env(rng)
    for k, e in (("1", e1), ("2", e2)):
        await h.set_glob("a" + k, e.a)
        await h.set_glob("d" + k, e.d)
        await h.set_glob("s" + k, e.s)
        await h.set_glob("r" + k, e.r)
    await h.set_glob("pm", rng.randrange(-(1 << 17), 1 << 17))
    await h.set_glob("cm", rng.randrange(-(1 << 17), 1 << 17))
    await h.set_glob("am", rng.randrange(1 << 17))
    await h.set_glob("hsync", rng.randrange(4))
    for v in range(NV):
        await h.set_voice(v, "pitch1", rng.randrange(1_400_000, 1_900_000))
        await h.set_voice(v, "pitch2", rng.randrange(1_400_000, 1_900_000))
        await h.set_voice(v, "vel_amp", rng.randrange(1 << 17))
        await h.set_voice(v, "cut_ofs", rng.randrange(-(1 << 17), 1 << 17))


@cocotb.test()
async def bit_exact_random(dut):
    rng = random.Random(11)
    await setup(dut)
    h = Harness(dut, rng)
    mism = 0
    for scene in range(4):
        await randomize(h, rng)
        for n in range(700):
            if n % 97 == 0:  # gates on / off / retrigger
                for v in range(NV):
                    r = h.m.regs[v]
                    val = rng.choice([0, 1, 1 | ((r.retrig ^ 1) << 1)])
                    await h.set_voice(v, "gate", val)
            if n == 350:
                h.am_ext = rng.randrange(1 << 17)
                dut.am_ext.value = h.am_ext
                await h.set_glob("am", h.am_reg)  # refresh model am
                h.m.g.pw_mod = rng.randrange(-(1 << 16), 1 << 16)
                dut.pw_ext.value = h.m.g.pw_mod
            rtl, ref = await h.sample(int(n % 53 == 7))  # SYNC edges: hard sync
            if rtl != ref:
                mism += 1
                assert mism < 5, f"scene {scene} sample {n}: rtl {rtl} model {ref}"
    assert mism == 0


@cocotb.test()
async def status_and_timing(dut):
    rng = random.Random(5)
    await setup(dut)
    h = Harness(dut, rng)
    await h.set_glob("a1", voice.env_coef(0.001, FS, True))
    await h.set_voice(2, "pitch1", 1_650_000)
    await h.set_voice(2, "gate", 1)
    # samples must finish well within the 2048-clk sample period
    d = dut
    d.tick.value = 1
    await RisingEdge(d.clk)
    d.tick.value = 0
    cycles = 0
    while not d.s0_valid.value:
        await RisingEdge(d.clk)
        cycles += 1
    assert cycles <= 22 * NV + 8
    for _ in range(200):
        await h.sample()
    st = await h.bus.read((2 << 6) | (5 << 2))
    assert (st >> 20) & 3 in (voice.ATTACK, voice.DECAY)
    assert st & 0x3FFFF > 0
    info = await h.bus.read((1 << 16) | (21 << 2))
    assert info == NV
    await ClockCycles(dut.clk, 2)


def test_voice_engine():
    rtlrun.run("voice_engine",
               rtlrun.rtl("voice/voice_engine.sv", "audio/pitch2inc.sv", "audio/exp2_rom.sv",
                          "audio/sine_quarter_rom.sv"),
               {"NUM_VOICES": NV}, module=__name__)
