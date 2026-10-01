"""Exponential ADSR envelope (float reference for the RTL envelope generator).

Segments are one-pole approaches to a target:
    attack  -- towards ATTACK_TARGET > 1, stops at 1.0 exactly after `attack` seconds from 0;
    decay   -- towards `sustain`, the remaining distance is 1e-3 (-60 dB) after `decay` seconds;
    release -- towards 0, the same -60 dB definition for `release`.
Gate re-trigger restarts the attack from the current level (no click).
"""

import math

import numpy as np

ATTACK_TARGET = 1.3
DECAY_RATIO = 1e-3
SILENCE = 1e-5

IDLE, ATTACK, DECAY, RELEASE = range(4)


def _coef(tau_s: float, fs_hz: float) -> float:
    return 1.0 - math.exp(-1.0 / (tau_s * fs_hz))


def attack_tau(attack_s: float) -> float:
    return attack_s / -math.log(1.0 - 1.0 / ATTACK_TARGET)


def decay_tau(time_s: float) -> float:
    return time_s / -math.log(DECAY_RATIO)


def adsr(gate, fs_hz: float, attack: float, decay: float, sustain: float, release: float) -> np.ndarray:
    """Envelope for a per-sample gate array (truthy = key held). Returns float array in [0, 1]."""
    gate = np.asarray(gate, dtype=bool)
    ca = _coef(attack_tau(attack), fs_hz)
    cd = _coef(decay_tau(decay), fs_hz)
    cr = _coef(decay_tau(release), fs_hz)
    out = np.empty(len(gate))
    env, state, prev = 0.0, IDLE, False
    for i, g in enumerate(gate):
        if g and not prev:
            state = ATTACK
        elif not g and prev:
            state = RELEASE
        prev = g
        if state == ATTACK:
            env += (ATTACK_TARGET - env) * ca
            if env >= 1.0:
                env, state = 1.0, DECAY
        elif state == DECAY:
            env += (sustain - env) * cd
        elif state == RELEASE:
            env -= env * cr
            if env < SILENCE:
                env, state = 0.0, IDLE
        out[i] = env
    return out


def gate_signal(n: int, fs_hz: float, notes) -> np.ndarray:
    """Gate array of n samples from [(on_s, off_s), ...]."""
    g = np.zeros(n, dtype=bool)
    for on, off in notes:
        g[int(round(on * fs_hz)):int(round(off * fs_hz))] = True
    return g
