"""External memory: SDRAM controller against an SDRAM model that checks command timing;
arbiter + block RAM backend with two random masters."""

import random

import cocotb
from cocotb.triggers import ClockCycles, FallingEdge

import rtlrun
from tbutil import start

# SDRAM device limits (W9864G6-class, -6 grade) in clocks of 99 MHz, rounded up
T_RP, T_RCD, T_RC, T_WR, T_MRD = 2, 2, 6, 2, 2
REF_MAX = 1544  # 15.6 us: 4096 rows in 64 ms
CL = 2
INIT_CYC = 198  # T_INIT_US = 2 in the test build
CMDS = {0b0111: "NOP", 0b0011: "ACT", 0b0101: "RD", 0b0100: "WR", 0b0010: "PRE", 0b0001: "REF", 0b0000: "MRS"}


class SdramModel:
    """Samples commands at falling edges (they are registered on rising edges), drives read data
    so it is valid at the rising edge CL clocks after the command."""

    def __init__(self, dut, rng):
        self.dut, self.rng = dut, rng
        self.mem = {}
        self.cyc = 0
        self.bank = [dict(row=None, last_act=-1000, idle_at=0, rcd_at=0) for _ in range(4)]
        self.init_step = 0  # PRE, REF, REF, MRS
        self.ready = False
        self.last_ref = None
        self.max_ref_gap = 0
        self.busy_until = 0  # REF / MRS / PRE-all: no command before
        self.rd_queue = {}
        self.rd_queue_done = set()
        self.counts = {}
        self.errors = []

    def err(self, msg):
        self.errors.append(f"cycle {self.cyc}: {msg}")

    async def run(self):
        d = self.dut
        while True:
            await FallingEdge(d.clk)
            self.cyc += 1
            if self.cyc in self.rd_queue:
                d.sd_dq_i.value = self.rd_queue.pop(self.cyc)
            elif self.cyc - 1 in self.rd_queue_done:
                d.sd_dq_i.value = self.rng.getrandbits(32)  # data hold ends
            if d.rst.value:
                continue
            c = CMDS.get((int(d.sd_cs_n.value) << 3) | (int(d.sd_ras_n.value) << 2) | (int(d.sd_cas_n.value) << 1)
                         | int(d.sd_we_n.value), "?")
            if int(d.sd_dq_oe.value) and c != "WR":
                self.err(f"DQ driven during {c}")
            if c == "NOP":
                continue
            self.counts[c] = self.counts.get(c, 0) + 1
            if not int(d.sd_cke.value):
                self.err("command with CKE low")
            if self.cyc < self.busy_until:
                self.err(f"{c} too early after REF/MRS/PRE")
            a, ba = int(d.sd_addr.value), int(d.sd_ba.value)
            b = self.bank[ba]
            if not self.ready:
                expect = ["PRE", "REF", "REF", "MRS"][self.init_step]
                if c != expect:
                    self.err(f"init: {c}, expected {expect}")
                if self.init_step == 0 and self.cyc < INIT_CYC:
                    self.err("init wait too short")
                self.init_step += 1
            if c == "PRE":
                if not a & (1 << 10):
                    self.err("PRE of one bank not expected")
                self.busy_until = self.cyc + T_RP
            elif c == "REF":
                if any(x["row"] is not None or self.cyc < x["idle_at"] or self.cyc - x["last_act"] < T_RC
                       for x in self.bank):
                    self.err("REF with a bank not idle")
                if self.ready and self.last_ref is not None:
                    self.max_ref_gap = max(self.max_ref_gap, self.cyc - self.last_ref)
                self.last_ref = self.cyc
                self.busy_until = self.cyc + T_RC
            elif c == "MRS":
                if a != (CL << 4):
                    self.err(f"mode register {a:#x}")
                self.busy_until = self.cyc + T_MRD
                self.ready = True
            elif c == "ACT":
                if not self.ready:
                    self.err("ACT before init")
                if b["row"] is not None or self.cyc < b["idle_at"]:
                    self.err("ACT on a busy bank")
                if self.cyc - b["last_act"] < T_RC:
                    self.err("tRC")
                b.update(row=a, last_act=self.cyc, rcd_at=self.cyc + T_RCD)
            elif c in ("RD", "WR"):
                if b["row"] is None:
                    self.err(f"{c} on an idle bank")
                    continue
                if self.cyc < b["rcd_at"]:
                    self.err("tRCD")
                if not a & (1 << 10):
                    self.err("no auto precharge")
                key = (ba, b["row"], a & 0xFF)
                if c == "WR":
                    if not int(d.sd_dq_oe.value):
                        self.err("WR without DQ")
                    old, new, dqm = self.mem.get(key, 0), int(d.sd_dq_o.value), int(d.sd_dqm.value)
                    mask = sum(0xFF << (8 * i) for i in range(4) if not dqm >> i & 1)
                    self.mem[key] = (old & ~mask) | (new & mask)
                    b["idle_at"] = self.cyc + T_WR + T_RP
                else:
                    if int(d.sd_dqm.value):
                        self.err("RD with DQM set")
                    self.rd_queue[self.cyc + CL] = self.mem.get(key, 0)
                    self.rd_queue_done.add(self.cyc + CL)
                    b["idle_at"] = self.cyc + 1 + T_RP
                b["row"] = None
            else:
                self.err(f"bad command {c}")


@cocotb.test()
async def sdram_random(dut):
    for s in ("req", "we", "addr", "wdata", "be", "sd_dq_i"):
        getattr(dut, s).value = 0
    rng = random.Random(7)
    model = SdramModel(dut, rng)
    cocotb.start_soon(model.run())
    await start(dut)
    for _ in range(400):
        await FallingEdge(dut.clk)
        if dut.ready.value:
            break
    assert dut.ready.value, "no init"
    ref = {}
    addrs = [(ba << 19) | (row << 8) | col for ba in range(4) for row in (0, 1, 2047) for col in (0, 5, 255)]
    n_rd = 0
    for n in range(1500):
        a = rng.choice(addrs) if rng.random() < 0.8 else rng.getrandbits(21)
        we = rng.random() < 0.5
        be = rng.choice([0xF, 0xF, 0x1, 0x6, 0x8, 0x0])
        wd = rng.getrandbits(32)
        dut.req.value, dut.we.value, dut.addr.value, dut.wdata.value, dut.be.value = 1, int(we), a, wd, be
        for _ in range(100):
            await FallingEdge(dut.clk)
            if dut.ack.value:
                break
        else:
            raise AssertionError("no ack")
        dut.req.value = 0
        if we:
            mask = sum(0xFF << (8 * i) for i in range(4) if be >> i & 1)
            ref[a] = (ref.get(a, 0) & ~mask) | (wd & mask)
        else:
            n_rd += 1
            got = int(dut.rdata.value)
            assert got == ref.get(a, 0), f"read {a:#x}: {got:#x} != {ref.get(a, 0):#x}"
        for _ in range(rng.choice([0, 0, 1, 3])):
            await FallingEdge(dut.clk)
    await ClockCycles(dut.clk, 2000)  # idle: refreshes only
    assert not model.errors, "\n".join(model.errors[:10])
    assert model.counts.get("REF", 0) > 10 and model.max_ref_gap <= REF_MAX, (model.counts, model.max_ref_gap)
    assert n_rd > 500


def test_sdram_ctrl():
    rtlrun.run("sdram_ctrl", rtlrun.rtl("mem/sdram_ctrl.sv"), {"T_INIT_US": 2},
               module=__name__, testcase="sdram_random")


# ------------------------------------------------------- arbiter + block RAM
async def master(dut, p, rng, ref, n, log):
    req, we, addr, wdata, be, ack = (getattr(dut, f"{p}_{s}") for s in ("req", "we", "addr", "wdata", "be", "ack"))
    for _ in range(n):
        a = rng.randrange(64)
        w = rng.random() < 0.5
        b = rng.choice([0xF, 0x3, 0x0])
        d = rng.getrandbits(32)
        req.value, we.value, addr.value, wdata.value, be.value = 1, int(w), a, d, b
        for _ in range(100):
            await FallingEdge(dut.clk)
            if ack.value:
                break
        else:
            raise AssertionError(f"{p}: no ack")
        req.value = 0
        # both masters share the memory, so the reference is updated at the ack
        if w:
            mask = sum(0xFF << (8 * i) for i in range(4) if b >> i & 1)
            ref[a] = (ref.get(a, 0) & ~mask) | (d & mask)
        else:
            got = int(dut.rdata.value)
            assert got == ref.get(a, 0), f"{p} read {a}: {got:#x} != {ref.get(a, 0):#x}"
        log.append(p)
        for _ in range(rng.choice([0, 1, 2])):
            await FallingEdge(dut.clk)


@cocotb.test()
async def arb_two_masters(dut):
    for p in "ab":
        for s in ("req", "we", "addr", "wdata", "be"):
            getattr(dut, f"{p}_{s}").value = 0
    await start(dut)
    ref, log = {}, []
    ta = cocotb.start_soon(master(dut, "a", random.Random(1), ref, 400, log))
    tb = cocotb.start_soon(master(dut, "b", random.Random(2), ref, 400, log))
    await ta
    await tb
    assert log.count("a") == 400 and log.count("b") == 400


def test_mem_arb_bram():
    rtlrun.run("mem_arb_bram_tb", [rtlrun.ROOT / "fpga/sim/unit/mem_arb_bram_tb.sv"]
               + rtlrun.rtl("mem/mem_arb.sv", "mem/mem_bram.sv"), module=__name__, testcase="arb_two_masters")
