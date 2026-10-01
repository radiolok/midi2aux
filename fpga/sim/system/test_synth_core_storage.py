"""Stage 9: SD card (TB model on the SD SPI pins, FAT16 image from sw/tools/fatimg.py):
presets from the console and the panel, firmware update from FIRMWARE.BIN to flash and booting it."""

import struct
import subprocess
import sys
import zlib

import vsys
from test_synth_core_soc import FW_FLASH, boot_core, fw_core

sys.path.insert(0, str(vsys.ROOT / "sw" / "tools"))
import fatimg  # noqa: E402


def make_image(name, files):
    src = []
    for n, data in files.items():
        p = vsys.BUILD / f"{name}_{n}"
        p.write_bytes(data)
        src.append(f"{n}={p}")
    img = vsys.BUILD / f"{name}.img"
    subprocess.run([sys.executable, str(vsys.ROOT / "sw/tools/fatimg.py"), "make", str(img), "16", *src], check=True)
    return img


def cmd(c, answer=None):
    return [f"sendline {c}", f"wait {answer or 'ok ' + c.split()[0]}"]


def test_presets_console_and_panel():
    img = make_image("sd_presets", {"README.TXT": b"AVK-6\n"})
    out = vsys.BUILD / "sd_presets_out.img"
    script = ["wait sd: fat16", "wait READY"]
    script += cmd("set cutoff 777", "ok cutoff") + cmd("set detune -13", "ok detune") + cmd("save 5")
    script += cmd("set cutoff 3000", "ok cutoff") + cmd("load 5") + cmd("get cutoff", "cutoff = 777")
    script += cmd("ls", "ok ls")
    # panel: last menu page (presets), preset 1, button 3 saves, button 2 loads
    script += ["enc 0 -1", "delay 25", "btn 2", "wait preset 1 save 0", "sendline set cutoff 100", "wait ok cutoff",
               "btn 1", "wait preset 1 load", "sendline get cutoff", "wait cutoff = 777"]
    r = vsys.run(fw_core(), "sd_presets", 0.5, uart_script=script, stop_on="cutoff = 777",
                 args=["--sd-image", str(img), "--sd-dump", str(out)])
    assert "file PRESET05.BIN" in r.uart and "file README.TXT 6" in r.uart
    f = fatimg.Fat(bytearray(out.read_bytes()))
    f.check()
    for n in ("PRESET05.BIN", "PRESET01.BIN"):
        rec = f.read(n)
        assert rec[:4] == b"AVKP"
        count = struct.unpack_from("<H", rec, 6)[0]
        vals = dict(struct.unpack_from("<Hh", rec, 8 + 4 * i) for i in range(count))
        # values keyed by a 16-bit FNV-1a hash of the parameter name
        h = 2166136261
        for ch in b"cutoff":
            h = ((h ^ ch) * 16777619) & 0xFFFFFFFF
        assert vals[(h ^ (h >> 16)) & 0xFFFF] == 777
    assert f.read("README.TXT") == b"AVK-6\n"


def test_no_card_is_reported():
    r = vsys.run(fw_core(), "sd_none", 0.2, uart_script=["wait READY"] + cmd("ls", "error: ls"), stop_on="error: ls")
    assert "sd: none" in r.uart


def test_firmware_update_from_sd_then_boot():
    sw = vsys.build_sw()
    fw = (sw / "fw.bin").read_bytes()
    img = make_image("sd_fw", {"FIRMWARE.BIN": fw})
    dump = vsys.BUILD / "sd_fw_flash.bin"
    boot = boot_core()
    # the boot loader runs the firmware from RAM (image in the RAM init), which updates the flash
    exe = vsys.build("synth_core", {"UART_BAUD": 1_000_000, "RESET_ADDR": 0, "RAM_INIT": sw / "fw.hex",
                                    "SIM_FAST": 1, "FW_FLASH_OFFSET": FW_FLASH}, defines=["SOC", "UART_BAUD=1000000"])
    r = vsys.run(exe, "sd_fwupdate", 1.5, uart_script=["wait READY"] + cmd("fwupdate", f"ok fwupdate {len(fw)}"),
                 stop_on=f"ok fwupdate {len(fw)}", args=["--sd-image", str(img)],
                 flash_dump=(dump, FW_FLASH, 0x10000))
    d = dump.read_bytes()
    assert struct.unpack("<III", d[:12]) == (0x464B5641, len(fw), zlib.crc32(fw))
    assert d[256:256 + len(fw)] == fw
    r = vsys.run(boot, "sd_fw_boot", 0.3, uart_script=[], stop_on="READY", flash_image=(dump, FW_FLASH))
    assert "boot from flash" in r.uart and "READY" in r.uart
