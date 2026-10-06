/* Boot loader (ROM). Protocol on the debug UART (host tool: sw/tools/load.py):
 *   host -> "AVKB"                           (magic; the firmware jumps here on it too)
 *   dev  -> "LOAD\n"
 *   host -> len:u32le flags:u32le image[len] crc32:u32le    (flags bit0: also write to flash)
 *   dev  -> "OK\n" and runs the image | "E1\n" bad length | "E2\n" bad CRC | "E3\n" flash verify
 * Without a host within SYSINFO_BOOT_WAIT ms it boots the image stored in SPI flash at
 * SYSINFO_FW_FLASH: header {magic "AVKF", len, crc} + image at +256. */
#include "hw.h"
#include "lib.h"

#define FLAG_FLASH 1u

static uint32_t ms_cycles(uint32_t ms) { return ms * (SYSINFO_SYS_CLK / 1000u); }

static void __attribute__((noreturn)) run_image(void)
{
    uart_flush();
    __asm__ volatile("jr %0" ::"r"(RAM_BASE));
    __builtin_unreachable();
}

/* 1 on "AVKB"; tmo = 0 waits forever */
static int wait_magic(uint32_t tmo)
{
    static const char magic[4] = {'A', 'V', 'K', 'B'};
    uint32_t t0 = cycles();
    int k = 0;
    while (!tmo || cycles() - t0 < tmo) {
        int c = uart_getc_nb();
        if (c < 0)
            continue;
        k = (c == magic[k]) ? k + 1 : (c == magic[0]);
        if (k == 4)
            return 1;
    }
    return 0;
}

static int get_u32(uint32_t *v)
{
    uint32_t r = 0;
    for (int i = 0; i < 4; i++) {
        int c = uart_getc_timeout(ms_cycles(1000));
        if (c < 0)
            return 0;
        r |= (uint32_t)c << (8 * i);
    }
    *v = r;
    return 1;
}

static uint32_t max_len(void) { return SYSINFO_RAM_BYTES - 2048u; }

static void save_to_flash(uint32_t len, uint32_t crc)
{
    uint32_t base = SYSINFO_FW_FLASH;
    struct fw_header h = {FW_MAGIC, len, crc};
    for (uint32_t a = 0; a < FW_HDR_SIZE + len; a += 4096)
        flash_erase_4k(SPI_FLASH, base + a);
    flash_program(SPI_FLASH, base + FW_HDR_SIZE, (const void *)RAM_BASE, len);
    flash_program(SPI_FLASH, base, &h, sizeof h);
}

static int flash_image_crc(uint32_t len, uint32_t *crc)
{
    uint8_t buf[64];
    uint32_t c = 0, base = SYSINFO_FW_FLASH + FW_HDR_SIZE;
    for (uint32_t a = 0; a < len; a += sizeof buf) {
        uint32_t n = len - a < sizeof buf ? len - a : sizeof buf;
        flash_read(SPI_FLASH, base + a, buf, n);
        c = crc32_update(c, buf, n);
    }
    *crc = c;
    return 1;
}

static void uart_load(void)
{
    uint32_t len, flags, crc, c;
    volatile uint8_t *ram = (volatile uint8_t *)RAM_BASE;
    uart_puts("LOAD\n");
    if (!get_u32(&len) || !get_u32(&flags) || len == 0 || len > max_len()) {
        uart_puts("E1\n");
        return;
    }
    for (uint32_t i = 0; i < len; i++) {
        int ch = uart_getc_timeout(ms_cycles(1000));
        if (ch < 0) {
            uart_puts("E1\n");
            return;
        }
        ram[i] = (uint8_t)ch;
    }
    if (!get_u32(&crc) || crc32((const void *)RAM_BASE, len) != crc) {
        uart_puts("E2\n");
        return;
    }
    if (flags & FLAG_FLASH) {
        save_to_flash(len, crc);
        if (!flash_image_crc(len, &c) || c != crc) {
            uart_puts("E3\n");
            return;
        }
    }
    uart_puts("OK\n");
    run_image();
}

static void flash_boot(void)
{
    struct fw_header h;
    uint32_t base = SYSINFO_FW_FLASH;
    flash_read(SPI_FLASH, base, &h, sizeof h);
    if (h.magic != FW_MAGIC || h.len == 0 || h.len > max_len()) {
        uart_puts("no image in flash\n");
        return;
    }
    flash_read(SPI_FLASH, base + FW_HDR_SIZE, (void *)RAM_BASE, h.len);
    if (crc32((const void *)RAM_BASE, h.len) != h.crc) {
        uart_puts("flash image CRC error\n");
        return;
    }
    uart_puts("boot from flash\n");
    run_image();
}

void boot_main(int loader_requested)
{
    uart_puts("\nAVK6 boot\n");
    if (loader_requested) {
        uart_load();
    } else {
        if (wait_magic(ms_cycles(SYSINFO_BOOT_WAIT)))
            uart_load();
        flash_boot();
    }
    uart_puts("waiting for image\n");
    for (;;)
        if (wait_magic(0))
            uart_load();
}
