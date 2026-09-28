"""Stage 5: panel -- encoders and knobs drive the menu and parameters, the display shows it.
The ST7789 model framebuffer is compared pixel by pixel with a reference rendering."""

import numpy as np

import lcdimg
import vsys

UART_BAUD = 1_000_000


def core():
    sw = vsys.build_sw()
    return vsys.build("synth_core", {"UART_BAUD": UART_BAUD, "RESET_ADDR": 0, "RAM_INIT": sw / "fw.hex",
                                     "NUM_VOICES": 2, "SIM_FAST": 1},
                      defines=["SOC", f"UART_BAUD={UART_BAUD}"])


def check_screen(r, dump, png):
    grid = lcdimg.parse_screen(r.uart)
    got = lcdimg.load_dump(dump)
    lcdimg.save_png(got, png)
    ref = lcdimg.render_ui(grid, lcdimg.load_font())
    bad = np.count_nonzero(got != ref)
    assert bad == 0, f"{bad} pixels differ from the reference rendering"
    return grid


def test_menu_encoders_and_knobs():
    dump = vsys.BUILD / "panel_lcd.bin"
    script = ["wait READY",
              "sendline screen", "wait screen end",
              "enc 0 3", "delay 25", "sendline screen", "wait screen end",    # MENU: page 4 (ФИЛЬТР)
              "enc 1 1", "enc 3 -2", "delay 25",                          # PAR1: lp -> bp, PAR3: env2 -96 ct
              "sendline get fmode", "wait fmode =",
              "pot 0 4095", "delay 30",                                   # CUTOFF knob to the top
              "sendline get cutoff", "wait cutoff =",
              "sendline screen", "wait screen end"]
    r = vsys.run(core(), "panel", 0.3, uart_script=script, stop_on="screen end", lcd_dump=dump)
    log = r.uart
    blocks = log.split("screen 0 ")
    assert "|< ГЕНЕРАТОРЫ  1/13 >" in blocks[1]
    assert "|< ФИЛЬТР  4/13 >" in blocks[2]
    assert "fmode = 1 (bp)" in log
    assert "cutoff = 16000 (16000 Hz)" in log
    grid = check_screen(r, dump, r.out_dir / "panel_lcd.png")
    assert grid[0].startswith("< ФИЛЬТР  4/13 >")
    assert grid[2].startswith("1 Фильтр") and grid[2].rstrip().endswith("bp")
    assert grid[6].rstrip().endswith("2304 ct")
    assert grid[7].startswith("Срез: 16000 Hz")


def test_menu_button_returns_to_first_page():
    dump = vsys.BUILD / "panel_btn_lcd.bin"
    script = ["wait READY", "enc 0 -1", "delay 25", "sendline screen", "wait screen end",
              "btn 0", "delay 40", "sendline screen", "wait screen end"]
    r = vsys.run(core(), "panel_btn", 0.2, uart_script=script, stop_on="screen end", lcd_dump=dump)
    blocks = r.uart.split("screen 0 ")
    assert "|< СЛОТЫ: k, FX MIX  13/13 >" in blocks[1]
    assert "|< ГЕНЕРАТОРЫ  1/13 >" in blocks[2]
    check_screen(r, dump, r.out_dir / "panel_btn_lcd.png")
