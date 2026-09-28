/* Firmware, stage 2: prints MIDI events and system info; "AVKB" on the UART
 * re-enters the boot loader to load a new image. */
#include "hw.h"
#include "lib.h"

static const char *const ev_names[8] = {"note_off", "note_on", "poly_at", "cc",
                                        "program", "chan_at", "bend", "system"};

static void print_event(uint32_t ev)
{
    uint8_t st = ev >> 16, d1 = ev >> 8, d2 = ev;
    xprintf("midi: %02x %02x %02x %s", st, d1, d2, ev_names[(st >> 4) & 7]);
    if (st < 0xF0)
        xprintf(" ch=%u", (st & 15u) + 1);
    xprintf("\n");
}

static void __attribute__((noreturn)) enter_loader(void)
{
    uart_flush();
    __asm__ volatile("jr %0" ::"r"(BOOTROM_BASE + 4));
    __builtin_unreachable();
}

static void poll_loader_magic(void)
{
    static int k;
    static const char magic[4] = {'A', 'V', 'K', 'B'};
    int c = uart_getc_nb();
    if (c < 0)
        return;
    k = (c == magic[k]) ? k + 1 : (c == magic[0]);
    if (k == 4)
        enter_loader();
}

int main(void)
{
    uint32_t clk = SYSINFO_SYS_CLK, half = SYSINFO_BCK_HALF;
    uint32_t fs_mhz = (uint32_t)(((uint64_t)clk * 1000u) / (128u * half));
    xprintf("AVK6 synth fw, hw version %08x\n", (unsigned)SYSINFO_VERSION);
    xprintf("sys_clk %u Hz, fs %u.%03u Hz, RAM %u bytes\n", (unsigned)clk, (unsigned)(fs_mhz / 1000),
            (unsigned)(fs_mhz % 1000), (unsigned)SYSINFO_RAM_BYTES);
    xprintf("READY\n");

    uint32_t t_led = cycles();
    for (;;) {
        uint32_t ev = MIDI_EVENT;
        if (ev & MIDI_EV_VALID)
            print_event(ev & 0xFFFFFFu);
        if (MIDI_STATUS & MIDI_ST_OVERFLOW) {
            xprintf("midi: overflow\n");
            MIDI_CTRL = 1;
        }
        poll_loader_magic();
        if (cycles() - t_led > clk / 2) {
            t_led = cycles();
            GPIO_OUT ^= 1u;
        }
    }
}
