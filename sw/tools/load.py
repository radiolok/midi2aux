#!/usr/bin/env python3
"""Load firmware into the synth over the debug UART (Tang Nano BL702 USB bridge).

    python3 sw/tools/load.py /dev/ttyUSB1 build/sw/fw.bin           # run from RAM
    python3 sw/tools/load.py /dev/ttyUSB1 build/sw/fw.bin --flash   # and save to SPI flash

The running firmware and the boot ROM both react to the "AVKB" magic; if the board
hangs, press reset -- the tool keeps sending the magic until the loader answers.
Needs pyserial (pip install pyserial).
"""

import argparse
import struct
import sys
import time
import zlib

MAGIC = b"AVKB"
FLAG_FLASH = 1


def build_payload(image: bytes, flash: bool = False) -> bytes:
    """len:u32le flags:u32le image crc32:u32le (after the device answered LOAD)."""
    return struct.pack("<II", len(image), FLAG_FLASH if flash else 0) + image + struct.pack("<I", zlib.crc32(image))


def read_until(port, token: bytes, timeout: float) -> bytes:
    buf = b""
    t0 = time.time()
    while time.time() - t0 < timeout:
        buf += port.read(port.in_waiting or 1)
        if token in buf:
            return buf
    raise TimeoutError(f"no {token!r} from the device, got {buf[-200:]!r}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("port")
    p.add_argument("image")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--flash", action="store_true", help="also write the image to SPI flash")
    p.add_argument("--timeout", type=float, default=30.0)
    a = p.parse_args()

    import serial  # noqa: PLC0415

    image = open(a.image, "rb").read()
    with serial.Serial(a.port, a.baud, timeout=0.1) as port:
        t0 = time.time()
        while True:
            port.write(MAGIC)
            try:
                read_until(port, b"LOAD", 0.5)
                break
            except TimeoutError:
                if time.time() - t0 > a.timeout:
                    sys.exit("loader did not answer (press reset on the board?)")
        port.write(build_payload(image, a.flash))
        reply = read_until(port, b"\n", 10 + len(image) * 12 / a.baud + (5 if a.flash else 0))
        if b"OK" not in reply:
            sys.exit(f"loader error: {reply!r} (E1 length, E2 CRC, E3 flash verify)")
        print(f"loaded {len(image)} bytes{' and saved to flash' if a.flash else ''}")
        try:  # show what the firmware prints
            while True:
                sys.stdout.write(port.read(256).decode(errors="replace"))
                sys.stdout.flush()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
