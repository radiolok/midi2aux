/* Firmware: polyphonic synth driven by MIDI; UART console (fw/console.h).
 * The log (UART) is non-blocking; "AVKB" on the UART re-enters the boot loader. */
#include "hw.h"
#include "lib.h"
#include "console.h"
#include "disp.h"
#include "storage.h"
#include "synth.h"

static struct synth synth;
static struct ui ui;
static struct storage storage;

/* SD card on SPI block 11 */
#define SPI_SD 11
static uint8_t sd_xfer(void *ctx, uint8_t b)
{
    (void)ctx;
    SPI_DATA(SPI_SD) = b;
    while (SPI_STATUS(SPI_SD) & 1u)
        ;
    return (uint8_t)SPI_DATA(SPI_SD);
}
static void sd_select(void *ctx, int on)
{
    (void)ctx;
    SPI_CS(SPI_SD) = (uint32_t)on;
}
static void sd_speed(void *ctx, int fast)
{
    (void)ctx;
    SPI_DIV(SPI_SD) = fast ? 2u : SYSINFO_SYS_CLK / 800000u; /* 16.5 MHz / 400 kHz at 99 MHz */
}
static const struct sd sd_hw = {sd_xfer, sd_select, sd_speed, 0, 0, 0};

static void preset_request(void)
{
    char line[32];
    int n = (int)synth.p.v[P_PRESET], load = ui.request == UI_REQ_LOAD;
    int r = load ? storage_load(&storage, &synth, n) : storage_save(&storage, &synth, n);
    ui.request = UI_REQ_NONE;
    if (r < 0)
        xsnprintf(line, sizeof line, "Пресет %d: ошибка %d", n, r);
    else
        xsnprintf(line, sizeof line, load ? "Пресет %d загружен" : "Пресет %d записан", n);
    log_printf("preset %d %s %d\n", n, load ? "load" : "save", r);
    if (load && r >= 0)
        ui_refresh(&ui);
    ui_status(&ui, line);
}

static const char *const ev_names[8] = {"note_off", "note_on", "poly_at", "cc",
                                        "program", "chan_at", "bend", "system"};

static void __attribute__((noreturn)) enter_loader(void)
{
    log_flush();
    __asm__ volatile("jr %0" ::"r"(BOOTROM_BASE + 4));
    __builtin_unreachable();
}

/* UART input: the boot loader magic "AVKB" or console lines */
static void poll_uart(void)
{
    static int k;
    static const char magic[4] = {'A', 'V', 'K', 'B'};
    int c;
    while ((c = uart_getc_nb()) >= 0) { /* drain: the RX FIFO is short */
        k = (c == magic[k]) ? k + 1 : (c == magic[0]);
        if (k == 4)
            enter_loader();
        console_feed((char)c);
    }
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
    if (st < 0xF0) {
        char line[32];
        xsnprintf(line, sizeof line, "MIDI %02x %02x %02x", st, d1, d2);
        ui_status(&ui, line);
    }
}

static void poll_panel(uint32_t now_ms)
{
    struct ui_input in;
    for (int k = 0; k < 4; k++)
        in.enc[k] = (int16_t)ENC_COUNT(k);
    in.pressed = (uint8_t)ENC_PRESSED;
    if (in.pressed)
        ENC_PRESSED = in.pressed;
    for (int k = 0; k < UI_POTS; k++)
        in.pot[k] = (uint16_t)(POT(k) >> 4);
    ui_update(&ui, &in, now_ms);
}

int main(void)
{
    struct fs_info fs = {SYSINFO_SYS_CLK, SYSINFO_BCK_HALF};
    uint32_t nv = SYSINFO_NUM_VOICES;
    uint32_t fs_mhz = (uint32_t)(((uint64_t)fs.sys_clk * 1000u) / (128u * fs.bck_half));
    synth_init(&synth, (int)(nv > VA_MAX_VOICES ? VA_MAX_VOICES : nv), fs);
    disp_init();
    ui_init(&ui, &synth);
    for (int k = 0; k < 4; k++) /* counters keep running across a firmware reload */
        ui.enc_prev[k] = (int16_t)ENC_COUNT(k);
    console_init(&synth, &ui);
    console_set_storage(&storage, sd_hw);

    log_printf("AVK6 synth fw, hw version %08x\n", (unsigned)SYSINFO_VERSION);
    log_printf("sys_clk %u Hz, fs %u.%03u Hz, RAM %u bytes, %u voices\n", (unsigned)fs.sys_clk,
         (unsigned)(fs_mhz / 1000), (unsigned)(fs_mhz % 1000), (unsigned)SYSINFO_RAM_BYTES, (unsigned)nv);
    int sd = storage_mount(&storage, sd_hw);
    if (sd)
        log_printf("sd: none (%d)\n", sd);
    else
        log_printf("sd: fat%d\n", storage.fat.fat32 ? 32 : 16);
    log_printf("READY\n");

    uint32_t t_led = cycles(), t_panel = cycles(), ms = 0;
    const uint32_t ms_cycles = fs.sys_clk / 1000u;
    for (;;) {
        uint32_t ev = MIDI_EVENT;
        if (ev & MIDI_EV_VALID)
            handle_event(ev & 0xFFFFFFu);
        if (MIDI_STATUS & MIDI_ST_OVERFLOW) {
            log_printf("midi: overflow\n");
            MIDI_CTRL = 1;
        }
        avk_poll(&synth);
        if (ui.request)
            preset_request();
        log_poll();
        ui_poll(&ui);
        poll_uart();
        if (cycles() - t_panel > 10 * ms_cycles) { /* panel every 10 ms */
            t_panel += 10 * ms_cycles;
            ms += 10;
            poll_panel(ms);
        }
        if (cycles() - t_led > fs.sys_clk / 2) {
            t_led = cycles();
            GPIO_OUT ^= 1u;
        }
    }
}
