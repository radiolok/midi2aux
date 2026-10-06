"""Audio timing derived from sys_clk. Mirrors fpga/rtl/audio/audio_clkgen.sv.

fs = sys_clk / (2 * bck_half * 64): BCK = 64 * fs (I2S, 32-bit slots),
bck_half = sys_clk cycles per BCK half-period.
"""

BCK_PER_FRAME = 64


def bck_half(sys_clk_hz: int, fs_hz: int) -> int:
    """Nearest integer BCK half-period (same integer formula as the RTL)."""
    return (sys_clk_hz + 64 * fs_hz) // (128 * fs_hz)


def fs_actual(sys_clk_hz: int, half: int) -> float:
    return sys_clk_hz / (2 * half * BCK_PER_FRAME)


def phase_inc(tone_hz: int, sys_clk_hz: int, half: int, phase_w: int = 32) -> int:
    """Rounded NCO increment for an integer tone at the actual fs (as in stub_core.sv)."""
    return ((1 << phase_w) * tone_hz * 2 * half * BCK_PER_FRAME + sys_clk_hz // 2) // sys_clk_hz


def phase_inc_hz(freq_hz: float, fs_hz: float, phase_w: int = 32) -> int:
    """Rounded NCO increment for an arbitrary frequency (note tables)."""
    return int(round(freq_hz * (1 << phase_w) / fs_hz)) % (1 << phase_w)


def note_hz(note: int, a4_hz: float = 440.0) -> float:
    """MIDI note number -> frequency, equal temperament."""
    return a4_hz * 2.0 ** ((note - 69) / 12.0)
