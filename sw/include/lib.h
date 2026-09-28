/* Small freestanding runtime shared by the boot loader and the firmware. */
#ifndef LIB_H
#define LIB_H

#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>

/* UART */
void uart_putc(char c);
void uart_puts(const char *s);
int  uart_getc_nb(void);                 /* -1 if nothing received */
int  uart_getc_timeout(uint32_t cycles); /* -1 on timeout */
void uart_flush(void);
int  uart_try_putc(char c);              /* 0 if the TX FIFO is full */

/* non-blocking log: formats into a ring buffer, log_poll() moves it to the UART */
void log_printf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
void log_poll(void);
void log_flush(void);

/* printf subset: %d %i %u %x %X %c %s %p %%, flags '0' '-', width, 'l' ignored */
int  xvsnprintf(char *buf, size_t n, const char *fmt, va_list ap);
int  xsnprintf(char *buf, size_t n, const char *fmt, ...) __attribute__((format(printf, 3, 4)));
int  xprintf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

/* CRC-32 (IEEE 802.3, as zlib.crc32) */
uint32_t crc32_update(uint32_t crc, const void *data, size_t len);
static inline uint32_t crc32(const void *data, size_t len) { return crc32_update(0, data, len); }

/* SPI NOR flash on SPI block `spi` */
void flash_read(int spi, uint32_t addr, void *dst, size_t len);
void flash_erase_4k(int spi, uint32_t addr);
void flash_program(int spi, uint32_t addr, const void *src, size_t len); /* any length, page-split */
uint32_t flash_jedec_id(int spi);

/* string.h subset (gcc may call these implicitly) */
void *memcpy(void *d, const void *s, size_t n);
void *memmove(void *d, const void *s, size_t n);
void *memset(void *d, int c, size_t n);
int   memcmp(const void *a, const void *b, size_t n);
size_t strlen(const char *s);
int   strcmp(const char *a, const char *b);

/* firmware image in flash: header at FW_FLASH offset, image at +FW_HDR_SIZE */
#define FW_MAGIC    0x464B5641u /* "AVKF" */
#define FW_HDR_SIZE 256u
struct fw_header {
    uint32_t magic;
    uint32_t len;
    uint32_t crc;
};

#endif
