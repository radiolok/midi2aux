/* Panel UI on a fake display (text grid). */
#include <stdlib.h>

#include "unity_lite.h"

#include "../fw/font.c"
#include "../fw/font8x16.c"
#include "../fw/params.c"
#include "../fw/patch.c"
#include "../fw/synth.c"
#include "../fw/ui.c"
#include "../fw/voice_alloc.c"
#include "../lib/xprintf.c"

static uint32_t regs[3 * 16384];
static uint32_t idx(uint32_t a) { return ((a >> 16) & 3) * 16384 + ((a & 0xFFFF) >> 2); }
void hw_write(uint32_t a, uint32_t v) { regs[idx(a)] = v; }
uint32_t hw_read(uint32_t a) { return regs[idx(a)]; }
void uart_putc(char c) { (void)c; }

static struct synth s;
static struct ui u;
static struct ui_input in;
static const struct fs_info FS = {99000000u, 16u};

/* fake display: code points on an 8x16 cell grid, plus a glyph counter; the FIFO can be
 * made "full" to check that drawing resumes later */
static uint32_t screen[UI_ROWS][UI_COLS];
static int glyph_calls, fifo_room = 1 << 30;
void disp_init(void) {}
void disp_fill(int x, int y, int w, int h, uint16_t c) { (void)x, (void)y, (void)w, (void)h, (void)c; }
int disp_glyph(int x, int y, uint32_t cp, uint16_t fg, uint16_t bg)
{
    (void)fg, (void)bg;
    CHECK((y - 3) % 16 == 0 && x % 8 == 0 && x < 240);
    if (fifo_room <= 0)
        return 0;
    fifo_room--;
    glyph_calls++;
    screen[(y - 3) / 16][x / 8] = cp;
    return 1;
}

static void update(uint32_t ms)
{
    ui_update(&u, &in, ms);
    ui_poll(&u);
}

static char rowbuf[UI_COLS * 3 + 1];
static const char *row(int r) /* screen row as UTF-8 without trailing spaces */
{
    char *p = rowbuf;
    for (int c = 0; c < UI_COLS; c++) {
        uint32_t cp = screen[r][c] ? screen[r][c] : ' ';
        if (cp < 0x80)
            *p++ = (char)cp;
        else if (cp < 0x800) {
            *p++ = (char)(0xC0 | (cp >> 6));
            *p++ = (char)(0x80 | (cp & 0x3F));
        } else {
            *p++ = (char)(0xE0 | (cp >> 12));
            *p++ = (char)(0x80 | ((cp >> 6) & 0x3F));
            *p++ = (char)(0x80 | (cp & 0x3F));
        }
    }
    while (p > rowbuf && p[-1] == ' ')
        p--;
    *p = 0;
    return rowbuf;
}

static void setup(void)
{
    memset(regs, 0, sizeof regs);
    memset(screen, 0, sizeof screen);
    memset(&in, 0, sizeof in);
    for (int k = 0; k < UI_POTS; k++)
        in.pot[k] = 2048;
    fifo_room = 1 << 30;
    synth_init(&s, 4, FS);
    ui_init(&u, &s);
    update(0); /* initial pot positions */
}

static void test_first_page(void)
{
    setup();
    CHECK_STR(row(0), "< ГЕНЕРАТОРЫ  1/8 >");
    CHECK_STR(row(2), "1 ГЕН1 форма               saw");
    CHECK_STR(row(4), "2 ГЕН2 форма               saw");
    CHECK_STR(row(6), "3 ГЕН2 расстр.            7 ct");
    CHECK_STR(row(7), "");
    char buf[UI_COLS * 3 + 1];
    ui_row_text(&u, 2, buf, sizeof buf);
    CHECK_STR(buf, "1 ГЕН1 форма               saw");
    CHECK_EQ(u.ndirty, 0);
}

static void test_page_navigation(void)
{
    setup();
    in.enc[ENC_MENU] = 3;
    update(10);
    CHECK_STR(row(0), "< ФИЛЬТР  4/8 >");
    in.enc[ENC_MENU] = -1; /* 4 back: wraps to the last page */
    update(20);
    CHECK_STR(row(0), "< ОБЩЕЕ  8/8 >");
    in.pressed = 1; /* MENU button: first page */
    update(30);
    in.pressed = 0;
    CHECK_STR(row(0), "< ГЕНЕРАТОРЫ  1/8 >");
}

static void test_edit_parameters(void)
{
    setup();
    in.enc[ENC_PAR1] = 2; /* saw -> tri */
    in.enc[ENC_PAR3] = -10;
    update(10);
    CHECK_EQ(s.p.v[P_WAVE1], 2);
    CHECK_EQ(hw_read(SYNTH_REG(S_WAVES)), 2);
    CHECK_STR(row(2), "1 ГЕН1 форма               tri");
    CHECK_EQ(s.p.v[P_DETUNE], -3);
    int before = glyph_calls;
    update(20); /* nothing changed: nothing redrawn */
    CHECK_EQ(glyph_calls, before);
    in.enc[ENC_PAR1] = 3; /* only the changed cells are sent: "tri" -> "sine" */
    update(30);
    CHECK_EQ(glyph_calls - before, 4);
}

static void test_drawing_resumes_when_fifo_frees(void)
{
    setup();
    fifo_room = 5;
    in.enc[ENC_MENU] = 3; /* new page: many cells change */
    update(10);
    CHECK_EQ(glyph_calls >= 5, 1);
    CHECK(u.ndirty > 0);
    CHECK(strcmp(row(0), "< ФИЛЬТР  4/8 >") != 0); /* not finished yet */
    fifo_room = 1 << 30;
    ui_poll(&u);
    CHECK_EQ(u.ndirty, 0);
    CHECK_STR(row(0), "< ФИЛЬТР  4/8 >");
}

static void test_steps(void)
{
    CHECK_EQ(ui_step(P_CUTOFF, 1000, 1), 1062);
    CHECK_EQ(ui_step(P_CUTOFF, 20, -1), 20);
    CHECK_EQ(ui_step(P_A1, 5, 1), 6);
    CHECK_EQ(ui_step(P_ENV2_AMT, 0, 1), 48);
    CHECK_EQ(ui_step(P_WAVE1, 3, 1), 3);
}

static void test_pots(void)
{
    setup();
    CHECK_EQ(ui_pot_value(0, 0), 20);
    CHECK_EQ(ui_pot_value(0, 4095), 16000);
    CHECK_EQ(ui_pot_value(0, 4085), 16000); /* dead zone at the end */
    CHECK_EQ(ui_pot_value(0, 10), 20);
    int32_t mid = ui_pot_value(0, 2048); /* exponential: geometric mean ~ 566 Hz */
    CHECK(mid > 540 && mid < 590);
    CHECK_EQ(ui_pot_value(2, 0), -4800);
    CHECK_EQ(ui_pot_value(6, 4095), 100);
    CHECK_EQ(ui_pot_value(4, 0), 1);
    CHECK(ui_pot_value(4, 4095) >= 9990);
    CHECK_EQ(s.p.v[P_CUTOFF], 4000); /* the initial position does not override the patch */
    /* hysteresis: +2 LSB is ignored, +3 applies and shows a popup */
    in.pot[0] = 2050;
    update(100);
    CHECK_STR(row(7), "");
    in.pot[0] = 4095;
    update(110);
    CHECK_EQ(s.p.v[P_CUTOFF], 16000);
    CHECK_STR(row(7), "Срез: 16000 Hz");
    update(2000); /* popup times out */
    CHECK_STR(row(7), "");
}

static void test_pot_updates_visible_param(void)
{
    setup();
    in.enc[ENC_MENU] = 7; /* page ОБЩЕЕ shows FX MIX, also on pot 4 */
    update(10);
    in.pot[3] = 0;
    update(20);
    CHECK_STR(row(6), "3 FX MIX" "                   0 %");
}

int main(void)
{
    RUN(test_first_page);
    RUN(test_page_navigation);
    RUN(test_edit_parameters);
    RUN(test_drawing_resumes_when_fifo_frees);
    RUN(test_steps);
    RUN(test_pots);
    RUN(test_pot_updates_visible_param);
    return TEST_RESULT();
}
