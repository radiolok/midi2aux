"""Regression: ADSR2 decaying to sustain 0 used to wrap the envelope below zero in RTL
(cutoff jumps, clicks). 2 voices, cutoff 150 Hz, Q 3, ENV2 +4 octaves; 15000 samples bit-exact."""

import random

import cocotb

import rtlrun
from synthmodel import pitch, voice
from test_voice_engine import FS, Harness, setup


@cocotb.test()
async def env2_decay_to_zero(dut):
    await setup(dut)
    h = Harness(dut, random.Random(0))
    h.m.n = 2
    e1 = voice.env_params(0.005, 0.3, 0.7, 0.3, FS)
    e2 = voice.env_params(0.001, 0.15, 0.0, 0.3, FS)
    regs = {"g1": 32768, "g2": 32768, "cutoff": voice.cutoff_pitch(150, FS), "env2_depth": 262144,
            "res_q": voice.res_q(3.0), "master": 16384,
            "a1": e1.a, "d1": e1.d, "s1": e1.s, "r1": e1.r, "a2": e2.a, "d2": e2.d, "s2": e2.s, "r2": e2.r}
    for k, v in regs.items():
        await h.set_glob(k, v)
    p = pitch.log2_q16(pitch.inc_for_hz(440, 99_000_000, 16)) - 2 * 65536  # A2
    for k, v in (("pitch1", p), ("pitch2", p + 382), ("vel_amp", 65536), ("gate", 1)):
        await h.set_voice(0, k, v)
    bad = 0
    for n in range(15000):
        rtl, ref = await h.sample()
        if rtl != ref:
            bad += 1
            if bad < 5:
                dut._log.error(f"n={n} rtl {rtl} model {ref}")
    assert bad == 0, bad


def test_voice_engine_regress():
    rtlrun.run("voice_engine",
               rtlrun.rtl("voice/voice_engine.sv", "audio/pitch2inc.sv", "audio/exp2_rom.sv",
                          "audio/sine_quarter_rom.sv"),
               {"NUM_VOICES": 2}, module=__name__)
