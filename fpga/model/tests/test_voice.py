import math

import numpy as np

from synthmodel import adsr, analysis, clocks, pitch, voice
from synthmodel.voice import VoiceEngine

FS = clocks.fs_actual(99_000_000, clocks.bck_half(99_000_000, 48_000))
P_A4 = pitch.log2_q16(pitch.inc_for_hz(440, 99_000_000, 16))


def engine(n=1, **g):
    e = VoiceEngine(n)
    for k, v in g.items():
        setattr(e.g, k, v)
    return e


def test_coef_pack_roundtrip():
    for c in (1.0, 0.5, 0.03, 1e-3, 1.43e-5, 3e-9):
        m, s = voice.unpack_coef(voice.coef_pack(c))
        assert 1 << 16 <= m < 1 << 17 or c >= 0.99
        assert abs(m * 2.0 ** -(14 + s) / c - 1) < 2e-5


def test_envelope_matches_float_model():
    a, d, s, r = 0.01, 0.1, 0.5, 0.2
    e = engine(env1=voice.env_params(a, d, s, r, FS))
    n = int(0.6 * FS)
    gate = adsr.gate_signal(n, FS, [(0.0, 0.3)])
    lev = []
    for i in range(n):
        e.regs[0].gate = int(gate[i])
        e.voice(0, e.g)
        lev.append(e.st[0].e1 / voice.ONE30)
    ref = adsr.adsr(gate, FS, a, d, s, r)
    assert np.max(np.abs(np.array(lev) - ref)) < 2e-3
    assert e.st[0].st1 == voice.IDLE and e.st[0].e1 == 0


def test_long_release_reaches_idle():
    e = engine(env1=voice.env_params(0.001, 0.001, 1.0, 10.0, FS))
    e.regs[0].gate = 1
    for _ in range(200):
        e.voice(0, e.g)
    e.regs[0].gate = 0
    for i in range(int(12 * FS)):
        e.voice(0, e.g)
        if e.st[0].st1 == voice.IDLE:
            break
    assert 9.9 < i / FS < 10.1


def test_oscillator_pitch_and_waves():
    for w in (voice.SAW, voice.SQUARE, voice.TRI, voice.SINE):
        e = engine(wave1=w, env1=voice.env_params(0.001, 0.001, 1.0, 0.01, FS), res_q=voice.res_q(0.707))
        e.regs[0].pitch1 = pitch.note_pitch(57, P_A4)  # 220 Hz
        e.regs[0].gate = 1
        out = np.array(e.run(int(0.2 * FS)))[2000:] / 65536
        assert abs(analysis.fundamental(out, FS) / 220 - 1) < 1e-3, w
        assert 0.5 < np.max(np.abs(out)) <= 1.1  # SVF (Q 0.707) overshoot on edges


def test_filter_lowpass_attenuates_saw_harmonics():
    base = dict(wave1=voice.SAW, env1=voice.env_params(0.001, 0.001, 1.0, 0.01, FS), res_q=voice.res_q(0.707))
    levels = {}
    for fc in (300.0, 5000.0):
        e = engine(cutoff=voice.cutoff_pitch(fc, FS), **base)
        e.regs[0].pitch1 = pitch.note_pitch(45, P_A4)  # 110 Hz
        e.regs[0].gate = 1
        out = np.array(e.run(int(0.2 * FS)))[3000:] / 65536
        h = analysis.harmonics_db(out, FS, 110.0, 20)
        levels[fc] = h[18]  # 20th harmonic, 2200 Hz
    assert levels[300.0] < levels[5000.0] - 30


def test_filter_response_near_chamberlin_float():
    # impulse through the fixed-point SVF vs float Chamberlin at 2x oversampling
    fc = 1000.0
    f = voice.svf_coef(voice.cutoff_pitch(fc, FS)) / 65536
    assert abs(f / (2 * math.sin(math.pi * fc / (2 * FS))) - 1) < 5e-3


def test_resonance_self_oscillates():
    e = engine(wave1=voice.SAW, g1=0, gn=1 << 12, env1=voice.env_params(0.001, 0.001, 1.0, 0.01, FS),
               cutoff=voice.cutoff_pitch(1000.0, FS), res_q=0)
    e.regs[0].gate = 1
    out = np.array(e.run(int(0.3 * FS)))[-8000:] / 65536
    assert np.max(np.abs(out)) > 0.3
    assert abs(analysis.fundamental(out, FS) / 1000 - 1) < 0.03


def test_polyphony_sum_and_master():
    e = engine(2, wave1=voice.SINE, env1=voice.env_params(0.001, 0.001, 1.0, 0.01, FS),
               res_q=voice.res_q(0.707), master=1 << 15)
    for v, note in enumerate((69, 76)):
        e.regs[v].pitch1 = pitch.note_pitch(note, P_A4)
        e.regs[v].gate = 1
    out = np.array(e.run(int(0.3 * FS)))[3000:] / 65536
    fr, db = analysis.spectrum_db(out, FS)
    for f0 in (440.0, 440 * 2 ** (7 / 12)):
        k = int(round(f0 / (fr[1] - fr[0])))
        assert np.max(db[k - 3:k + 4]) > -12  # each sine at ~0.5


def test_retrigger_toggle_restarts_attack():
    e = engine(env1=voice.env_params(0.01, 0.05, 0.5, 0.2, FS))
    e.regs[0].gate = 1
    for _ in range(int(0.2 * FS)):
        e.voice(0, e.g)
    assert e.st[0].st1 == voice.DECAY
    e.regs[0].retrig ^= 1
    e.voice(0, e.g)
    assert e.st[0].st1 == voice.ATTACK
    e.voice(0, e.g)
    assert e.st[0].st1 == voice.ATTACK  # a toggle retriggers once
