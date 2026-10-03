/* ST7789 1.14" 135 x 240 IPS panel in landscape through the lcd_ctrl stream controller. */
#include "disp.h"
#include "font.h"
#include "hw.h"
#include "lib.h"

#define X_OFS 40          /* panel RAM offsets in landscape (rotation 1) */
#define Y_OFS 53
#define HW_FIFO 64
#define GLYPH_ENTRIES 21  /* window 11 + colours 2 + bitmap 8 */

static uint16_t cur_fg = 0xFFFF, cur_bg = 0x0000; /* controller colours after its reset */

static void put(uint32_t entry)
{
    while (LCD_STATUS & LCD_ST_FULL)
        ;
    LCD_FIFO = entry;
}

static void wait_idle(void)
{
    while (LCD_STATUS & LCD_ST_BUSY)
        ;
}

static void delay_ms(uint32_t ms)
{
    uint32_t n = ms * (SYSINFO_SYS_CLK / 1000u), t0 = cycles();
    if (SYSINFO_FLAGS & 1u) /* simulation: the display model needs no reset delays */
        n /= 100;
    while (cycles() - t0 < n)
        ;
}

static void cmd(uint8_t c, const uint8_t *data, int n)
{
    put(LCD_CMD(c));
    for (int i = 0; i < n; i++)
        put(LCD_DATA(data[i]));
}

static void window(int x, int y, int w, int h)
{
    uint16_t x0 = (uint16_t)(x + X_OFS), x1 = (uint16_t)(x + w - 1 + X_OFS);
    uint16_t y0 = (uint16_t)(y + Y_OFS), y1 = (uint16_t)(y + h - 1 + Y_OFS);
    uint8_t ca[4] = {(uint8_t)(x0 >> 8), (uint8_t)x0, (uint8_t)(x1 >> 8), (uint8_t)x1};
    uint8_t ra[4] = {(uint8_t)(y0 >> 8), (uint8_t)y0, (uint8_t)(y1 >> 8), (uint8_t)y1};
    cmd(0x2A, ca, 4);   /* CASET */
    cmd(0x2B, ra, 4);   /* RASET */
    put(LCD_CMD(0x2C)); /* RAMWR */
}

static void colours(uint16_t fg, uint16_t bg)
{
    if (fg != cur_fg)
        put(LCD_COLOR_FG(fg));
    if (bg != cur_bg)
        put(LCD_COLOR_BG(bg));
    cur_fg = fg;
    cur_bg = bg;
}

void disp_init(void)
{
    static const uint8_t colmod = 0x55, madctl = 0x60; /* 16 bpp; MX | MV = landscape */
    LCD_DIV = 1;
    LCD_CTRL = 0;
    delay_ms(10);
    LCD_CTRL = 1; /* out of reset */
    delay_ms(120);
    cmd(0x01, 0, 0); /* SWRESET */
    wait_idle();
    delay_ms(150);
    cmd(0x11, 0, 0); /* SLPOUT */
    wait_idle();
    delay_ms(10);
    cmd(0x3A, &colmod, 1);
    cmd(0x36, &madctl, 1);
    cmd(0x21, 0, 0); /* INVON: IPS panel */
    cmd(0x13, 0, 0); /* NORON */
    cmd(0x29, 0, 0); /* DISPON */
    disp_fill(0, 0, DISP_W, DISP_H, 0);
    LCD_CTRL = 3; /* backlight on */
}

void disp_fill(int x, int y, int w, int h, uint16_t color)
{
    if (w <= 0 || h <= 0)
        return;
    colours(color, cur_bg);
    window(x, y, w, h);
    put(LCD_FILL((uint32_t)(w * h)));
    wait_idle();
}

int disp_glyph(int x, int y, uint32_t cp, uint16_t fg, uint16_t bg)
{
    if ((LCD_STATUS & 0xFFu) > HW_FIFO - GLYPH_ENTRIES)
        return 0;
    const uint8_t *g = font_glyph(cp);
    colours(fg, bg);
    window(x, y, FONT_W, FONT_H);
    for (int r = 0; r < FONT_H; r += 2) /* two 8-pixel rows per entry */
        put(LCD_BITS(16, (uint32_t)g[r] << 8 | g[r + 1]));
    return 1;
}
