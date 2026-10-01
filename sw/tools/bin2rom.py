#!/usr/bin/env python3
"""Raw binary -> SystemVerilog case ROM of 32-bit words (boot ROM for synth_core)."""
import argparse
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("bin", type=Path)
p.add_argument("sv", type=Path)
p.add_argument("--name", default="boot_rom")
p.add_argument("--aw", type=int, default=10, help="word address bits (10 = 4 KB)")
a = p.parse_args()

data = a.bin.read_bytes()
data += b"\0" * (-len(data) % 4)
words = [int.from_bytes(data[i:i + 4], "little") for i in range(0, len(data), 4)]
if len(words) > 1 << a.aw:
    raise SystemExit(f"{a.bin}: {len(data)} bytes do not fit into {4 << a.aw}")

lines = [
    "// GENERATED from sw/boot by sw/tools/bin2rom.py -- do not edit, run `make bootrom`.",
    f"// {len(data)} bytes of {4 << a.aw}.",
    "`default_nettype none",
    "",
    f"module {a.name} (",
    "    input  wire         clk,",
    f"    input  wire  [{a.aw - 1}:0]  addr,",
    "    output logic [31:0] data",
    ");",
    "",
    "    always_ff @(posedge clk) begin",
    "        case (addr)",
]
lines += [f"            {a.aw}'d{i}: data <= 32'h{w:08x};" for i, w in enumerate(words)]
lines += ["            default: data <= '0;", "        endcase", "    end", "", "endmodule", "",
          "`default_nettype wire", ""]
a.sv.write_text("\n".join(lines))
