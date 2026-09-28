"""Voice engine: bit-exact integer model of fpga/rtl/voice/voice_engine.sv.

Per sample, for every voice v = 0..N-1 in order (all shifts are arithmetic, floor):

1. Envelopes (ADSR1 -> amplitude, ADSR2 -> cutoff), level e: Q2.30 (1.0 = 2^30).
   Gate rising edge or a retrigger (RETRIG bit toggled by the CPU) -> ATTACK;
   falling edge -> RELEASE (unless IDLE).
   Segment = one-pole approach to a target T with coefficient (mant, shift):
       step = ((T - e) >> 14) * mant >> shift;  e += step
   ATTACK:  T = 1.3 (2^30 * 1.3), stops at 1.0 -> DECAY
   DECAY:   T = sustain << 14 (sustain Q0.16), stays there (sustain phase), e >= 0
   RELEASE: T = -1e-3 (so it ends at the -60 dB time), stops at 0 -> IDLE
   env_q = e >> 14 (Q2.16).
2. Oscillators: pitch = clamp21(PITCHk + pm); phase += pitch2inc(pitch);
   waves from the 32-bit phase, +-1.0 = +-2^16: saw, square/PWM (pw = clamp(PW + pw_mod, 0, 65535)),
   triangle, sine.
   Noise: 32-bit Galois LFSR (shared, one step per voice), n = (lfsr >> 15) - 2^16.
3. Mix: x = sat18((o1*G1 + o2*G2 + n*GN) >> 16).
4. Cutoff (log pitch units, like oscillators): c = clamp(CUTOFF + CUT_OFS + (env2_q*ENV2_DEPTH >> 16) + cm)
   x_c = pitch2inc(c) / 2^32 = fc / fs;  theta = pi/2 * x_c (2x oversampled SVF)
   f = 2 sin(theta) ~ 2 theta - theta^3 / 3   (Q1.16)
5. Damping q = min(RES_Q, 2 - f - 1/16) (Chamberlin stability), Q2.16.
6. Chamberlin SVF, two passes per sample, states 24-bit:
       lp += f*bp >> 16;  hp = x - lp - (q*bp >> 16);  bp += f*hp >> 16
   y = sat18(lp | bp | hp by FMODE).
7. VCA: a = sat18((env1_q * VEL_AMP >> 16) * am >> 16);  out = sat18(y * a >> 16).
8. sum += out.
Output S0 = sat20(sum * MASTER >> 16) (Q4.16, then the soft clipper, see softclip.py).
"""

from dataclasses import dataclass, field

from . import nco
from .pitch import pitch2inc

IDLE, ATTACK, DECAY, RELEASE = range(4)
ONE30 = 1 << 30
ATK_TARGET = 1395864371  # round(1.3 * 2^30)
REL_TARGET = -1075839  # -1e-3/(1-1e-3) * 2^30: e reaches 0 at the -60 dB time
PI_HALF_Q16 = 102944     # round(pi/2 * 2^16)
THIRD_Q16 = 21845        # floor(2^16 / 3)
C_MAX = 1995158          # cutoff pitch limit: fc = 0.34 fs
Q_MARGIN = 4096          # 1/16
SAW, SQUARE, TRI, SINE = range(4)
LP, BP, HP = range(3)
LFSR_TAPS = 0xD0000001   # x^32 + x^31 + x^29 + x + 1 (Galois, right shift)
PITCH_MAX = (1 << 21) - 1


def sat(x, bits):
    lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return lo if x < lo else hi if x > hi else x


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


@dataclass
class EnvParams:
    a: int = 0      # packed coefficient: shift << 17 | mant
    d: int = 0
    s: int = 0      # sustain Q0.16 (0..65536)
    r: int = 0


@dataclass
class GlobalParams:
    wave1: int = SAW
    wave2: int = SAW
    pw: int = 32768           # pulse width, fraction of the period * 2^16
    g1: int = 1 << 16         # mix gains Q2.16
    g2: int = 0
    gn: int = 0
    cutoff: int = C_MAX       # log pitch
    env2_depth: int = 0       # signed, pitch units per 1.0 of ADSR2
    res_q: int = 1 << 16      # damping (1/Q), Q2.16
    fmode: int = LP
    master: int = 1 << 16
    env1: EnvParams = field(default_factory=EnvParams)
    env2: EnvParams = field(default_factory=EnvParams)
    pm: int = 0               # global pitch offset (bend), signed
    cm: int = 0               # global cutoff offset, signed
    am: int = 1 << 16         # global amplitude, Q2.16
    pw_mod: int = 0           # pulse width offset from the modulation unit, signed


@dataclass
class VoiceRegs:
    pitch1: int = 0
    pitch2: int = 0
    gate: int = 0
    retrig: int = 0           # toggle bit: a change restarts the envelopes
    vel_amp: int = 1 << 16
    cut_ofs: int = 0


@dataclass
class VoiceState:
    ph1: int = 0
    ph2: int = 0
    e1: int = 0
    e2: int = 0
    st1: int = IDLE
    st2: int = IDLE
    gate_prev: int = 0
    rt_prev: int = 0
    lp: int = 0
    bp: int = 0


def unpack_coef(c):
    return c & 0x1FFFF, (c >> 17) & 31


def env_step(e, st, gate, gate_prev, retrig, p: EnvParams):
    if gate and (not gate_prev or retrig):
        st = ATTACK
    elif not gate and gate_prev and st != IDLE:
        st = RELEASE
    if st == IDLE:
        return 0, IDLE
    if st == ATTACK:
        t, c = ATK_TARGET, p.a
    elif st == DECAY:
        t, c = p.s << 14, p.d
    else:
        t, c = REL_TARGET, p.r
    mant, shift = unpack_coef(c)
    e += (((t - e) >> 14) * mant) >> shift
    if st == ATTACK and e >= ONE30:
        e, st = ONE30, DECAY
    elif st == RELEASE and e <= 0:
        e, st = 0, IDLE
    elif e < 0:  # DECAY to sustain 0 can step below zero (floor of (T - e) >> 14)
        e = 0
    return e, st


def wave(ph, w, pw):
    if w == SAW:
        return (ph >> 15) - (1 << 16)
    if w == SQUARE:
        return (1 << 16) if ph < (pw << 16) else -(1 << 16)
    if w == TRI:
        u = ph >> 15
        return 2 * u - (1 << 16) if u < (1 << 16) else 3 * (1 << 16) - 2 * u
    return int(nco.sine_int(ph)) >> 1


def lfsr_step(x):
    return (x >> 1) ^ (LFSR_TAPS if x & 1 else 0)


def svf_coef(c):
    """Cutoff log pitch -> (f Q1.16)."""
    inc = pitch2inc(c)
    theta = ((inc >> 15) * PI_HALF_Q16) >> 16          # theta * 2^17 = 2 theta in Q16
    th2 = (theta * theta) >> 17
    th3 = (th2 * theta) >> 17
    return theta - ((th3 * THIRD_Q16) >> 16)


class VoiceEngine:
    def __init__(self, num_voices, lfsr_seed=0x1):
        self.n = num_voices
        self.g = GlobalParams()
        self.regs = [VoiceRegs() for _ in range(num_voices)]
        self.st = [VoiceState() for _ in range(num_voices)]
        self.lfsr = lfsr_seed

    def voice(self, v, g: GlobalParams):
        r, s = self.regs[v], self.st[v]
        rt = r.retrig != s.rt_prev
        s.e1, s.st1 = env_step(s.e1, s.st1, r.gate, s.gate_prev, rt, g.env1)
        s.e2, s.st2 = env_step(s.e2, s.st2, r.gate, s.gate_prev, rt, g.env2)
        s.gate_prev, s.rt_prev = r.gate, r.retrig
        env1_q, env2_q = s.e1 >> 14, s.e2 >> 14

        s.ph1 = (s.ph1 + pitch2inc(clamp(r.pitch1 + g.pm, 0, PITCH_MAX))) & 0xFFFFFFFF
        s.ph2 = (s.ph2 + pitch2inc(clamp(r.pitch2 + g.pm, 0, PITCH_MAX))) & 0xFFFFFFFF
        pw = clamp(g.pw + g.pw_mod, 0, 65535)
        o1, o2 = wave(s.ph1, g.wave1, pw), wave(s.ph2, g.wave2, pw)
        self.lfsr = lfsr_step(self.lfsr)
        nz = (self.lfsr >> 15) - (1 << 16)
        x = sat((o1 * g.g1 + o2 * g.g2 + nz * g.gn) >> 16, 18)

        c = clamp(g.cutoff + r.cut_ofs + ((env2_q * g.env2_depth) >> 16) + g.cm, 0, C_MAX)
        f = svf_coef(c)
        q = min(g.res_q, (1 << 17) - f - Q_MARGIN)
        hp = 0
        for _ in range(2):
            s.lp = sat(s.lp + ((f * s.bp) >> 16), 24)
            hp = sat(x - s.lp - ((q * s.bp) >> 16), 24)
            s.bp = sat(s.bp + ((f * hp) >> 16), 24)
        y = sat((s.lp, s.bp, hp)[g.fmode] if g.fmode < 3 else s.lp, 18)

        a = sat((((env1_q * r.vel_amp) >> 16) * g.am) >> 16, 18)
        return sat((y * a) >> 16, 18)

    def sample(self):
        acc = sum(self.voice(v, self.g) for v in range(self.n))
        return sat((acc * self.g.master) >> 16, 20)

    def run(self, n):
        return [self.sample() for _ in range(n)]


# ------------------------------------------------------------------ parameter conversion (CPU side)
import math  # noqa: E402

ATK_RATIO = -math.log(1.0 - 1.0 / 1.3)
DEC_RATIO = math.log(1000.0)


def coef_pack(c: float) -> int:
    """Coefficient c in (0, 1] -> shift << 17 | mant with c = mant * 2^-(14 + shift), mant in [2^16, 2^17)."""
    shift = min(max(math.ceil(2 - math.log2(c)), 2), 31)
    mant = min(int(round(c * 2 ** (14 + shift))), (1 << 17) - 1)
    return (shift << 17) | mant


def env_coef(time_s: float, fs: float, attack=False) -> int:
    tau = time_s / (ATK_RATIO if attack else DEC_RATIO)
    return coef_pack(1.0 - math.exp(-1.0 / (tau * fs)))


def env_params(a, d, s, r, fs) -> EnvParams:
    return EnvParams(env_coef(a, fs, True), env_coef(d, fs), int(round(s * 65536)), env_coef(r, fs))


def cutoff_pitch(hz: float, fs: float) -> int:
    return clamp(int(round((math.log2(hz / fs) + 32) * 65536)), 0, C_MAX)


def res_q(q_factor: float) -> int:
    """Resonance Q (0.5..inf) -> damping 1/Q in Q2.16."""
    return clamp(int(round(65536 / q_factor)), 0, 1 << 17)
