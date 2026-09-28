"""Stage 2: synth_core SoC -- boot loader (UART, SPI flash), firmware prints MIDI events."""

import re
import struct
import sys
import zlib

import vsys
from synthmodel import midi

sys.path.insert(0, str(vsys.ROOT / "sw" / "tools"))
import load  # noqa: E402  host loader: its framing is what the boot ROM must accept

UART_BAUD = 1_000_000  # faster than the 115200 default to keep simulations short
FW_FLASH = 0x50_0000
SOC = ["SOC", f"UART_BAUD={UART_BAUD}"]


def payload(image: bytes, flags=0, crc=None):
    if crc is None:
        return load.build_payload(image, flash=bool(flags))
    return struct.pack("<II", len(image), flags) + image + struct.pack("<I", crc)


def boot_core(**extra):
    params = {"UART_BAUD": UART_BAUD, "BOOT_WAIT_MS": 1, "FW_FLASH_OFFSET": FW_FLASH, "SIM_FAST": 1, **extra}
    return vsys.build("synth_core", params, defines=SOC)


def fw_core():
    sw = vsys.build_sw()
    return vsys.build("synth_core", {"UART_BAUD": UART_BAUD, "RESET_ADDR": 0, "RAM_INIT": sw / "fw.hex", "SIM_FAST": 1},
                      defines=SOC)


def write_payload(name, data):
    p = vsys.BUILD / f"{name}.bin"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def test_fw_prints_midi_events():
    exe = fw_core()
    events = [(30.5, [0x90, 69, 100]), (31.5, [72, 0]), (32.5, [0xB3, 1, 64, 0xF8]), (33.5, [0xE0, 0, 0x40]),
              (34.5, [0xF0, 1, 2, 3, 0xF7, 0xC1, 5]), (35.5, [0xFC])]
    stim = vsys.write_midi(vsys.BUILD / "soc_midi.txt", events)
    r = vsys.run(exe, "soc_midi", 0.1, midi=stim, stop_on="fc 00 00 system", uart_script=[])
    assert "READY" in r.uart and "sys_clk 99000000 Hz, fs 48339.843 Hz" in r.uart
    got = [tuple(int(x, 16) for x in m) for m in re.findall(r"midi: (\w\w) (\w\w) (\w\w)", r.uart)]
    stream = [b for _, bs in events for b in bs]
    assert got == [e for e in midi.parse(stream) if e[0] not in (0xF8, 0xFE)]  # clock is not logged
    assert "note_on ch=1" in r.uart and "note_off ch=1" in r.uart


def test_boot_loads_image_over_uart():
    sw = vsys.build_sw()
    exe = boot_core()
    pl = write_payload("fw_payload", payload((sw / "fw.bin").read_bytes()))
    script = ["wait waiting for image", "sendstr AVKB", "wait LOAD", f"sendfile {pl}", "wait OK", "wait READY"]
    r = vsys.run(exe, "boot_uart", 0.6, uart_script=script, stop_on="READY")
    assert "no image in flash" in r.uart
    assert r.uart.index("OK") < r.uart.index("AVK6 synth fw")


def test_boot_rejects_bad_crc_then_retries():
    sw = vsys.build_sw()
    exe = boot_core()
    img = (sw / "fw.bin").read_bytes()
    bad = write_payload("fw_payload_badcrc", payload(img, crc=zlib.crc32(img) ^ 1))
    good = write_payload("fw_payload", payload(img))
    script = ["wait waiting for image", "sendstr AVKB", "wait LOAD", f"sendfile {bad}", "wait E2",
              "sendstr AVKB", "wait LOAD", f"sendfile {good}", "wait OK", "wait READY"]
    vsys.run(exe, "boot_badcrc", 0.8, uart_script=script, stop_on="READY")


def test_boot_writes_flash_and_boots_from_it():
    sw = vsys.build_sw()
    exe = boot_core()
    img = (sw / "fw.bin").read_bytes()
    pl = write_payload("fw_payload_flash", payload(img, flags=1))
    dump = vsys.BUILD / "flash_dump.bin"
    script = ["wait AVK6 boot", "sendstr AVKB", "wait LOAD", f"sendfile {pl}", "wait OK", "wait READY"]
    vsys.run(exe, "boot_to_flash", 0.8, uart_script=script, stop_on="READY",
             flash_dump=(dump, FW_FLASH, 0x10000))
    d = dump.read_bytes()
    magic, ln, crc = struct.unpack("<III", d[:12])
    assert (magic, ln, crc) == (0x464B5641, len(img), zlib.crc32(img))
    assert d[256:256 + len(img)] == img

    r = vsys.run(exe, "boot_from_flash", 0.3, uart_script=[], stop_on="READY", flash_image=(dump, FW_FLASH))
    assert "boot from flash" in r.uart


def test_fw_reenters_loader():
    sw = vsys.build_sw()
    exe = fw_core()
    pl = write_payload("fw_payload", payload((sw / "fw.bin").read_bytes()))
    script = ["wait READY", "sendstr AVKB", "wait LOAD", f"sendfile {pl}", "wait OK", "wait READY"]
    r = vsys.run(exe, "fw_reload", 0.6, uart_script=script, stop_on="READY")
    assert r.uart.count("READY") == 2
