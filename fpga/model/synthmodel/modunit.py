"""Modulation unit: 2 LFO + modulation matrix. Bit-exact model of fpga/rtl/voice/mod_unit.sv.

Once per sample (on audio_tick), in this order:
1. LFOk: phase += INC (u32); on wrap the random value is resampled (xorshift32,
   one step per wrap: LFO1 first). SYNC edge (sync_edge input) resets phases with SYNC_RESET set.
   Waves, Q2.16 (+-1.0 = +-65536), u = phase >> 15 (17 bit):
     0 sine (parabolic): t = triangle; y = (2t - t|t| / 2^16)   (max error ~6 %)
     1 triangle: 2u - 2^16 (u < 2^16) else 3*2^16 - 2u, shifted by a quarter period so it starts at 0
     2 saw up: u - 2^16      3 square: +1 / -1 (phase < 2^31)
     4 random S&H: (rng >> 15) - 2^16       5 saw down: 2^16 - 1 - u
2. Sources (Q2.16): 0 zero, 1 LFO1, 2 LFO2, 3 MODWHEEL, 4 IN1, 5 IN2, 6 SYNC (+-1), 7 ENV,
   8 GATE (0 / 1.0), 9 AUX (CPU register), others zero.
3. Routes k = 0..7 in order: v = (src * DEPTH) >> 16; if via: v = (sat25(v) * via) >> 16;
   acc[dst] += v. Destinations: 0 none, 1 PM (pitch units), 2 CM (pitch units), 3 AM (Q2.16),
   4 PW (fraction * 2^16).
4. Outputs: pm = sat23(acc_pm), cm = sat23(acc_cm), am = sat18(AM_BASE + acc_am), pw = sat17(acc_pw).
The voice engine latches the outputs at the next audio_tick (one sample later).
"""

from dataclasses import dataclass, field

SINE, TRI, SAW_UP, SQUARE, RANDOM, SAW_DOWN = range(6)
S_ZERO, S_LFO1, S_LFO2, S_MODWHEEL, S_IN1, S_IN2, S_SYNC, S_ENV, S_GATE, S_AUX = range(10)
D_NONE, D_PM, D_CM, D_AM, D_PW = range(5)
ONE = 1 << 16


def sat(x, bits):
    lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return lo if x < lo else hi if x > hi else x


def xorshift32(x):
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= x >> 17
    x ^= (x << 5) & 0xFFFFFFFF
    return x


@dataclass
class Route:
    src: int = S_ZERO
    via: int = S_ZERO   # S_ZERO here means "no via" (x 1.0)
    dst: int = D_NONE
    depth: int = 0      # signed, 24 bit


@dataclass
class Lfo:
    inc: int = 0
    wave: int = SINE
    sync_reset: int = 0
    phase: int = 0
    rnd: int = 0


def lfo_wave(ph, w, rnd):
    u = ph >> 15
    if w == SAW_UP:
        return u - ONE
    if w == SAW_DOWN:
        return ONE - 1 - u
    if w == SQUARE:
        return ONE if ph < (1 << 31) else -ONE
    if w == RANDOM:
        return rnd
    # triangle starting at 0 going up: shift the phase by a quarter period
    v = ((ph + (1 << 30)) & 0xFFFFFFFF) >> 15
    t = 2 * v - ONE if v < ONE else 3 * ONE - 2 * v
    if w == TRI:
        return t
    return 2 * t - ((t * abs(t)) >> 16)


@dataclass
class ModUnit:
    lfo: list = field(default_factory=lambda: [Lfo(), Lfo()])
    routes: list = field(default_factory=lambda: [Route() for _ in range(8)])
    modwheel: int = 0
    am_base: int = ONE
    aux: int = 0
    rng: int = 1
    out: tuple = (0, 0, ONE, 0)   # pm, cm, am, pw
    lfo_out: list = field(default_factory=lambda: [0, 0])

    def step(self, in1=0, in2=0, sync=0, sync_edge=0, env=0, gate=0):
        for i, l in enumerate(self.lfo):
            if sync_edge and l.sync_reset:
                l.phase = 0
            else:
                nxt = l.phase + l.inc
                if nxt >> 32:
                    self.rng = xorshift32(self.rng)
                    l.rnd = (self.rng >> 15) - ONE
                l.phase = nxt & 0xFFFFFFFF
            self.lfo_out[i] = lfo_wave(l.phase, l.wave, l.rnd)
        src = [0, self.lfo_out[0], self.lfo_out[1], self.modwheel, in1, in2,
               ONE if sync else -ONE, env, ONE if gate else 0, self.aux]
        get = lambda s: src[s] if s < len(src) else 0  # noqa: E731
        acc = [0] * 5
        for r in self.routes:
            v = (get(r.src) * r.depth) >> 16
            if r.via:
                v = (sat(v, 25) * get(r.via)) >> 16
            acc[r.dst] += v
        self.out = (sat(acc[D_PM], 23), sat(acc[D_CM], 23), sat(self.am_base + acc[D_AM], 18),
                    sat(acc[D_PW], 17))
        return self.out
