/* SPI NOR flash: 03 read, 06 WREN, 20 4K erase, 02 page program, 05 RDSR, 9F JEDEC ID. */
#include "hw.h"
#include "lib.h"

static uint8_t xfer(int spi, uint8_t b)
{
    SPI_DATA(spi) = b;
    while (SPI_STATUS(spi) & 1u)
        ;
    return (uint8_t)SPI_DATA(spi);
}

static void cmd_addr(int spi, uint8_t cmd, uint32_t addr)
{
    SPI_CS(spi) = 1;
    xfer(spi, cmd);
    xfer(spi, (uint8_t)(addr >> 16));
    xfer(spi, (uint8_t)(addr >> 8));
    xfer(spi, (uint8_t)addr);
}

static void wren(int spi)
{
    SPI_CS(spi) = 1;
    xfer(spi, 0x06);
    SPI_CS(spi) = 0;
}

static void wait_ready(int spi)
{
    uint8_t st;
    do {
        SPI_CS(spi) = 1;
        xfer(spi, 0x05);
        st = xfer(spi, 0);
        SPI_CS(spi) = 0;
    } while (st & 1u);
}

void flash_read(int spi, uint32_t addr, void *dst, size_t len)
{
    uint8_t *p = dst;
    cmd_addr(spi, 0x03, addr);
    while (len--)
        *p++ = xfer(spi, 0);
    SPI_CS(spi) = 0;
}

void flash_erase_4k(int spi, uint32_t addr)
{
    wren(spi);
    cmd_addr(spi, 0x20, addr);
    SPI_CS(spi) = 0;
    wait_ready(spi);
}

void flash_program(int spi, uint32_t addr, const void *src, size_t len)
{
    const uint8_t *p = src;
    while (len) {
        size_t n = 256 - (addr & 255);
        if (n > len)
            n = len;
        wren(spi);
        cmd_addr(spi, 0x02, addr);
        for (size_t i = 0; i < n; i++)
            xfer(spi, p[i]);
        SPI_CS(spi) = 0;
        wait_ready(spi);
        addr += n;
        p += n;
        len -= n;
    }
}

uint32_t flash_jedec_id(int spi)
{
    SPI_CS(spi) = 1;
    xfer(spi, 0x9F);
    uint32_t id = (uint32_t)xfer(spi, 0) << 16;
    id |= (uint32_t)xfer(spi, 0) << 8;
    id |= xfer(spi, 0);
    SPI_CS(spi) = 0;
    return id;
}
