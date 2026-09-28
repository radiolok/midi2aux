"""Build and run Verilator system testbenches (fpga/sim/tb/tb_audio.cpp) from pytest."""

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from synthmodel import wavio

ROOT = Path(__file__).resolve().parents[3]
RTL = ROOT / "fpga" / "rtl"
TB = ROOT / "fpga" / "sim" / "tb"
BUILD = ROOT / "build" / "sim"

SYS_CLK_HZ = 99_000_000
DATA_W = 18

_built = {}


def rtl_files():
    lines = (RTL / "files.f").read_text().splitlines()
    return [RTL / ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def build(top, params=None, defines=(), tb="tb_audio.cpp", extra_sources=(), sys_clk=SYS_CLK_HZ):
    params = dict(params or {})
    params.setdefault("SYS_CLK_HZ", sys_clk)
    key = hashlib.sha1(repr((top, sorted(params.items()), defines, tb, extra_sources)).encode()).hexdigest()[:10]
    if key in _built:
        return _built[key]
    obj = BUILD / "obj" / f"{top}_{key}"
    obj.mkdir(parents=True, exist_ok=True)
    cflags = [f"-DSYS_CLK_HZ={sys_clk}", f"-DDATA_W={params.get('DATA_W', DATA_W)}",
              f"-DTOP_CLASS=V{top}", f"-DTOP_HEADER='\"V{top}.h\"'"] + [f"-D{d}" for d in defines]
    cmd = ["verilator", "--cc", "--exe", "--build", "-j", "0", "-Wall", "-O3", "--top-module", top,
           "-CFLAGS", "-O2 " + " ".join(cflags), "-Mdir", str(obj)]
    cmd += [f"-G{k}={v}" for k, v in params.items()]
    cmd += [str(f) for f in rtl_files()] + [str(s) for s in extra_sources] + [str(TB / tb)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    exe = obj / f"V{top}"
    _built[key] = exe
    return exe


@dataclass
class SimResult:
    tb: dict
    fs: float
    left: np.ndarray   # DAC codes, DATA_W bits
    right: np.ndarray
    wav: Path
    out_dir: Path
    stdout: str

    def t(self, i):
        """Time of sample i in seconds from the TB start (first frame completion + i frames)."""
        return (self.tb["first_frame_cycle"] + i * SYS_CLK_HZ / self.fs) / SYS_CLK_HZ

    def index(self, t_s):
        return int(round((t_s * SYS_CLK_HZ - self.tb["first_frame_cycle"]) * self.fs / SYS_CLK_HZ))


def run(exe, name, duration, midi=None, args=(), expect_ok=True):
    out = BUILD / name
    out.mkdir(parents=True, exist_ok=True)
    wav, js = out / f"{name}.wav", out / f"{name}_tb.json"
    cmd = [str(exe), "--duration", str(duration), "--wav", str(wav), "--json", str(js)]
    if midi is not None:
        cmd += ["--midi", str(midi)]
    cmd += list(args)
    p = subprocess.run(cmd, capture_output=True, text=True)
    print(p.stdout, p.stderr)
    tb = json.loads(js.read_text())
    if expect_ok:
        assert p.returncode == 0 and tb["ok"], f"testbench failed: {tb.get('first_error')}"
    _, data, bits = wavio.read_wav(wav)
    shift = bits - tb["data_w"]
    return SimResult(tb, tb["fs_hz"], data[:, 0] >> shift, data[:, 1] >> shift, wav, out, p.stdout)


def write_midi(path, events):
    """events: [(time_ms, [bytes...], comment), ...] -> stimulus file."""
    with open(path, "w") as f:
        for ev in events:
            t, bs = ev[0], ev[1]
            c = f"  # {ev[2]}" if len(ev) > 2 else ""
            f.write(f"{t:.3f} " + " ".join(f"{b:02X}" for b in bs) + c + "\n")
    return path


def midi_end_ms(t_ms, nbytes):
    """End of a message sent at t_ms (no queueing): 10 bits per byte at 31250 baud."""
    return t_ms + nbytes * 0.32
