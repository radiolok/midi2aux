/* Firmware, stage 3: polyphonic synth driven by MIDI.
 * The log (UART) is non-blocking; "AVKB" on the UART re-enters the boot loader. */
#include "hw.h"
#include "lib.h"
#include "synth.h"

static struct synth synth;

static const char *const ev_names[8] = {"note_off", "note_on", "poly_at", "cc",
                                        "program", "chan_at", "bend", "system"};

static void __attribute__((noreturn)) enter_loader(void)
{
    log_flush();
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

static void handle_event(uint32_t ev)
{
    uint8_t st = ev >> 16, d1 = ev >> 8, d2 = ev;
    int v = synth_midi(&synth, st, d1, d2);
    if (st == 0xF8 || st == 0xFE) /* clock / active sensing: too frequent to log */
        return;
    log_printf("midi: %02x %02x %02x %s", st, d1, d2, ev_names[(st >> 4) & 7]);
    if (st < 0xF0)
        log_printf(" ch=%u", (st & 15u) + 1);
    if (v >= 0)
        log_printf(" v=%d", v);
    log_printf("\n");
}

int main(void)
{
    struct fs_info fs = {SYSINFO_SYS_CLK, SYSINFO_BCK_HALF};
    uint32_t nv = SYSINFO_NUM_VOICES;
    uint32_t fs_mhz = (uint32_t)(((uint64_t)fs.sys_clk * 1000u) / (128u * fs.bck_half));
    synth_init(&synth, (int)(nv > VA_MAX_VOICES ? VA_MAX_VOICES : nv), fs, &default_patch);

    log_printf("AVK6 synth fw, hw version %08x\n", (unsigned)SYSINFO_VERSION);
    log_printf("sys_clk %u Hz, fs %u.%03u Hz, RAM %u bytes, %u voices\n", (unsigned)fs.sys_clk,
         (unsigned)(fs_mhz / 1000), (unsigned)(fs_mhz % 1000), (unsigned)SYSINFO_RAM_BYTES, (unsigned)nv);
    log_printf("READY\n");

    uint32_t t_led = cycles();
    for (;;) {
        uint32_t ev = MIDI_EVENT;
        if (ev & MIDI_EV_VALID)
            handle_event(ev & 0xFFFFFFu);
        if (MIDI_STATUS & MIDI_ST_OVERFLOW) {
            log_printf("midi: overflow\n");
            MIDI_CTRL = 1;
        }
        log_poll();
        poll_loader_magic();
        if (cycles() - t_led > fs.sys_clk / 2) {
            t_led = cycles();
            GPIO_OUT ^= 1u;
        }
    }
}
