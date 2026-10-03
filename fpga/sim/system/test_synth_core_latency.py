"""trs.md 6: MIDI -> sound latency <= 3 ms, measured while the menu is being redrawn
(encoder turns force page redraws: the display must never delay MIDI handling)."""

import numpy as np

import vsys

UART_BAUD = 1_000_000
LATENCY_MAX_MS = 3.0


def core():
    sw = vsys.build_sw()
    return vsys.build("synth_core", {"UART_BAUD": UART_BAUD, "RESET_ADDR": 0, "RAM_INIT": sw / "fw.hex",
                                     "SIM_FAST": 1, "NUM_VOICES": 2},
                      defines=["SOC", f"UART_BAUD={UART_BAUD}"])


def test_latency_under_display_load():
    notes = [150 + 10 * i for i in range(25)]  # every 10 ms: on, off 5 ms later
    events = []
    for i, t in enumerate(notes):
        n = 60 + (i % 12)
        events += [(t, [0x90, n, 100]), (t + 5, [0x80, n, 0])]
    stim = vsys.write_midi(vsys.BUILD / "latency_midi.txt", events)
    script = ["wait READY", "sendline set a1 1", "wait ok a1", "sendline set r1 1", "wait ok r1"]
    for k in range(20):  # keep the menu busy: page redraws every ~13 ms
        script += [f"enc 0 {1 if k % 2 == 0 else -1}", "delay 13"]
    r = vsys.run(core(), "latency", 0.43, midi=stim, uart_script=script)
    x = np.abs(r.left) / (65536 * 1.6)
    assert "midi: 90" in r.uart
    lat = []
    for t in notes:
        end = vsys.midi_end_ms(t, 3) / 1e3
        i = r.index(end)
        seg = x[i:r.index(end + 0.004)]
        on = np.flatnonzero(seg > 0.01)
        assert len(on), f"note at {t} ms: no sound within 4 ms"
        lat.append((r.t(i + on[0]) - end) * 1e3)
    assert max(lat) <= LATENCY_MAX_MS, lat
    print(f"latency ms: max {max(lat):.3f}, mean {np.mean(lat):.3f}")
