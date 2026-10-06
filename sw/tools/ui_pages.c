/* Host dump of every menu page as the firmware draws it (docs: images for README.md).
 * Output: "page N" and then "row R |text|" lines; build: see tools/readme_figs.py. */
#include <stdio.h>
#include <string.h>

#include "../fw/avk.c"
#include "../fw/font.c"
#include "../fw/font8x16.c"
#include "../fw/params.c"
#include "../fw/patch.c"
#include "../fw/synth.c"
#include "../fw/ui.c"
#include "../fw/voice_alloc.c"
#include "../lib/xprintf.c"
#include "../test/fake_regs.h"

void uart_putc(char c) { (void)c; }
void disp_init(void) {}
void disp_fill(int x, int y, int w, int h, uint16_t c) { (void)x, (void)y, (void)w, (void)h, (void)c; }
int disp_glyph(int x, int y, uint32_t cp, uint16_t fg, uint16_t bg)
{
    (void)x, (void)y, (void)cp, (void)fg, (void)bg;
    return 1;
}

static void dump(const struct ui *u)
{
    char row[UI_COLS * 3 + 1];
    for (int r = 0; r < UI_ROWS; r++) {
        ui_row_text(u, r, row, sizeof row);
        printf("row %d |%s|\n", r, row);
    }
}

int main(void)
{
    static struct synth s;
    static struct ui u;
    struct ui_input in;
    const struct fs_info fs = {99000000u, 16u};
    static const uint8_t types[] = {SLOT_MATH, SLOT_MATH, SLOT_DELAY, SLOT_DELAY, SLOT_CHORUS, SLOT_REVERB};
    for (int k = 0; k < 6; k++)
        regs[idx(SLOT_REG(k, SL_TYPE))] = types[k];
    regs[idx(SYSINFO_NUM_SLOTS)] = 6;
    regs[idx(SYSINFO_MEM_WORDS)] = 2u << 20;
    synth_init(&s, 32, fs);
    ui_init(&u, &s);
    memset(&in, 0, sizeof in);
    for (int k = 0; k < UI_POTS; k++)
        in.pot[k] = 2048;
    ui_update(&u, &in, 0);
    for (int p = 0; p < ui_num_pages; p++) {
        printf("page %d\n", p);
        dump(&u);
        in.enc[ENC_MENU]++;
        ui_update(&u, &in, 10u * (uint32_t)p + 10u);
    }
    /* a knob turned: the status line shows the new value */
    in.pot[0] = 3000;
    ui_update(&u, &in, 1000);
    printf("page knob\n");
    dump(&u);
    return 0;
}
