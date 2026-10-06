"""MIDI byte stream parser. Reference for fpga/rtl/midi/midi_parser.sv.

Events are (status, d1, d2):
  - channel messages 8n..En with running status; Note On with velocity 0 becomes
    Note Off 8n kk 40 (release velocity 64); 1-data messages (Cn, Dn) have d2 = 0;
  - System Realtime F8..FF are emitted immediately as (b, 0, 0), even inside a
    message, and do not touch running status;
  - System Common F0..F7 (incl. SysEx) are dropped with their data and clear
    running status; data bytes without a status are ignored.
"""


def data_len(status: int) -> int:
    hi = status & 0xF0
    return 1 if hi in (0xC0, 0xD0) else 2


def parse(stream):
    events = []
    running = 0  # 0 = none
    buf = []
    for b in stream:
        if b >= 0xF8:
            events.append((b, 0, 0))
        elif b >= 0xF0:
            running = 0
            buf = []
        elif b >= 0x80:
            running = b
            buf = []
        elif running:
            buf.append(b)
            if len(buf) == data_len(running):
                d1, d2 = buf[0], buf[1] if len(buf) > 1 else 0
                st = running
                if st & 0xF0 == 0x90 and d2 == 0:
                    st, d2 = 0x80 | (st & 0x0F), 0x40
                events.append((st, d1, d2))
                buf = []
    return events
