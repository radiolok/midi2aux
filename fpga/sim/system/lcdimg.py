"""ST7789 model dumps -> images; reference rendering of the firmware text UI (sw/fw/ui.c)."""

import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
FONT_C = ROOT / "sw" / "fw" / "font8x16.c"
FB_W, FB_H = 320, 240
X_OFS, Y_OFS = 40, 53     # panel offsets in landscape (sw/fw/lcd.c)
W, H = 240, 135


def rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


C_BG = rgb565(0, 0, 0)
C_TITLE, C_TBG = rgb565(255, 255, 255), rgb565(0, 60, 140)
C_VALUE, C_STATUS = rgb565(255, 220, 0), rgb565(0, 220, 220)
ROW_COLORS = {0: (C_TITLE, C_TBG), 2: (C_VALUE, C_BG), 4: (C_VALUE, C_BG), 6: (C_VALUE, C_BG),
              7: (C_STATUS, C_BG)}


def load_dump(path):
    fb = np.fromfile(path, dtype="<u2").reshape(FB_H, FB_W)
    return fb[Y_OFS:Y_OFS + H, X_OFS:X_OFS + W]


def to_rgb(img565):
    r = ((img565 >> 11) & 0x1F) * 255 // 31
    g = ((img565 >> 5) & 0x3F) * 255 // 63
    b = (img565 & 0x1F) * 255 // 31
    return np.stack([r, g, b], axis=-1).astype(np.uint8)


def save_png(img565, path, scale=3):
    import matplotlib.image as mpimg
    rgb = to_rgb(img565).repeat(scale, 0).repeat(scale, 1)
    mpimg.imsave(path, rgb)


def load_font():
    text = FONT_C.read_text()
    ranges = [(int(a, 16), int(b, 16), int(c)) for a, b, c in
              re.findall(r"\{0x([0-9A-F]+), 0x([0-9A-F]+), (\d+)\},", text)]
    glyphs = [[int(v, 16) for v in re.findall(r"0x([0-9A-F]{2})", row)]
              for row in re.findall(r"\{((?:0x[0-9A-F]{2}, ){15}0x[0-9A-F]{2})\}", text)]
    font = {}
    for lo, hi, first in ranges:
        if hi == 0:
            continue
        for cp in range(lo, hi + 1):
            font[cp] = glyphs[first + cp - lo]
    return font


def render_ui(grid, font):
    """Expected screen for the text grid (8 rows of 30 cells) as drawn by ui.c."""
    img = np.full((H, W), C_BG, dtype=np.uint16)
    for r, text in enumerate(grid):
        fg, bg = ROW_COLORS.get(r, (C_BG, C_BG))
        y = 3 + 16 * r
        for c, ch in enumerate(text[:30]):
            g = font.get(ord(ch), font[ord("?")])
            for yy in range(16):
                for xx in range(8):
                    img[y + yy, 8 * c + xx] = fg if (g[yy] >> (7 - xx)) & 1 else bg
    return img


def parse_screen(uart_text):
    """Last 'screen r |text|' block of the console output -> 8 strings."""
    rows = {}
    for r, t in re.findall(r"screen (\d) \|(.*?)\|\r?\n", uart_text):
        rows[int(r)] = t
    return [rows.get(r, "") for r in range(8)]
