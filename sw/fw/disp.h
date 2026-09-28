/* Display primitives (240 x 135 landscape, RGB565), implemented by lcd.c on the ST7789 and by
 * fakes in host tests. Only disp_glyph() is used while running: it never waits. */
#ifndef DISP_H_INCLUDED
#define DISP_H_INCLUDED

#include <stdint.h>

#define DISP_W 240
#define DISP_H 135
#define RGB565(r, g, b) ((uint16_t)((((r) & 0xF8) << 8) | (((g) & 0xFC) << 3) | ((b) >> 3)))

void disp_init(void);                                       /* blocking, clears the screen */
void disp_fill(int x, int y, int w, int h, uint16_t color); /* blocking */
/* one 8x16 glyph; returns 0 (nothing sent) if the controller FIFO has no room right now */
int disp_glyph(int x, int y, uint32_t cp, uint16_t fg, uint16_t bg);

#endif
