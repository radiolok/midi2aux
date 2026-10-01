"""pytest -> cocotb runner glue for RTL unit tests (Verilator).

Each test module holds the cocotb coroutines and a pytest function that calls
`run(top, sources, params, module=__name__)`. Builds are cached per (top, params)
in build/unit/.
"""

import hashlib
import xml.etree.ElementTree as ET
import os
import sys
from pathlib import Path

import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from cocotb.runner import get_runner

ROOT = Path(__file__).resolve().parents[3]
RTL = ROOT / "fpga" / "rtl"
MODEL = ROOT / "fpga" / "model"
BUILD = ROOT / "build" / "unit"

if str(MODEL) not in sys.path:
    sys.path.insert(0, str(MODEL))


def rtl(*names):
    return [RTL / n for n in names]


def run(top, sources, params=None, module=None, testcase=None, extra_env=None, waves=False):
    params = params or {}
    key = hashlib.sha1(repr((top, sorted(map(str, sources)), sorted(params.items()))).encode()).hexdigest()[:10]
    build_dir = BUILD / f"{top}_{key}"
    runner = get_runner("verilator")
    runner.build(
        sources=[str(s) for s in sources],
        hdl_toplevel=top,
        parameters=params,
        build_dir=str(build_dir),
        build_args=["-Wall", "-Wno-fatal", "-Wno-DECLFILENAME", "--x-assign", "unique", "--x-initial", "unique"]
        + (["--trace-fst"] if waves else []),
        always=False,
    )
    env = {"PYTHONPATH": os.pathsep.join([str(Path(__file__).resolve().parent), str(MODEL)])}
    env.update(extra_env or {})
    # raises SystemExit if any cocotb test fails (under pytest); also make sure tests did run:
    # a test module that fails to import leaves no test cases in the results file
    results = runner.test(
        hdl_toplevel=top,
        test_module=module,
        testcase=testcase,
        build_dir=str(build_dir),
        test_dir=str(build_dir),
        extra_env=env,
        waves=waves,
    )
    cases = ET.parse(results).getroot().iter("testcase") if Path(results).exists() else []
    cases = list(cases)
    if not cases or any(c.find("failure") is not None or c.find("error") is not None for c in cases):
        raise SystemExit(f"cocotb: no test ran or a test failed ({results})")
