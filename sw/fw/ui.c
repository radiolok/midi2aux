#include "ui.h"

#include "disp.h"
#include "font.h"
#include "lib.h"

#define C_BG     RGB565(0, 0, 0)
#define C_TITLE  RGB565(255, 255, 255)
#define C_TBG    RGB565(0, 60, 140)
#define C_VALUE  RGB565(255, 220, 0)
#define C_STATUS RGB565(0, 220, 220)
#define ROW_Y(r) (3 + 16 * (r))
#define POT_DEAD 16 /* LSB of 12 bits */

struct page {
    const char *title;
    uint8_t p[3];
};

static const struct page pages[] = {
    {"ГЕНЕРАТОРЫ", {P_WAVE1, P_WAVE2, P_DETUNE}},
    {"ГЕН2 И СМЕСЬ", {P_OSC2_SEMI, P_MIX1, P_MIX2}},
    {"ШУМ, PWM, СИЛА", {P_NOISE, P_PW, P_VEL_AMP}},
    {"ФИЛЬТР", {P_FMODE, P_VEL_CUT, P_ENV2_AMT}},
    {"ADSR2 → СРЕЗ", {P_A2, P_D2, P_S2}},
    {"ADSR2, LFO1", {P_R2, P_LFO1_RATE, P_LFO1_WAVE}},
    {"LFO2, ВИБРАТО", {P_LFO2_RATE, P_LFO2_WAVE, P_VIBRATO}},
    {"ОБЩЕЕ", {P_BEND, P_MASTER, P_FX_MIX}},
};
const int ui_num_pages = sizeof pages / sizeof pages[0];

/* fixed potentiometers (panel order) and their curves */
enum { LIN, EXP };
static const struct {
    uint8_t param, curve;
} pots[UI_POTS] = {
    {P_CUTOFF, EXP}, {P_RES, EXP}, {P_ENV2_AMT, LIN}, {P_FX_MIX, LIN},
    {P_A1, EXP},     {P_D1, EXP},  {P_S1, LIN},       {P_R1, EXP},
};

int ui_pot_param(int pot) { return pots[pot].param; }

/* 2^x for 0 <= x <= 16, float, no libm: integer part by shifting, fraction by e^(x ln 2) */
static float exp2f_small(float x)
{
    int k = (int)x;
    float r = 1.0f / fexp_neg((x - (float)k) * 0.693147181f);
    while (k-- > 0)
        r *= 2.0f;
    return r;
}

static float log2f_ratio(int32_t hi, int32_t lo)
{
    /* log2(hi / lo) for hi >= lo > 0 from the 16.16 integer log2 */
    return ((float)log2_q16((uint64_t)hi << 16) - (float)log2_q16((uint64_t)lo << 16)) / 65536.0f;
}

int32_t ui_pot_value(int pot, int raw)
{
    const struct param_desc *d = &param_table[pots[pot].param];
    /* dead zones at both ends: the knob reaches min / max reliably */
    int r = raw < POT_DEAD ? 0 : raw > 4095 - POT_DEAD ? 4095 - 2 * POT_DEAD : raw - POT_DEAD;
    float x = (float)r / (float)(4095 - 2 * POT_DEAD);
    if (pots[pot].curve == LIN)
        return d->min + (int32_t)((float)(d->max - d->min) * x + 0.5f);
    return param_clamp(pots[pot].param, (int32_t)((float)d->min * exp2f_small(x * log2f_ratio(d->max, d->min)) + 0.5f));
}

int32_t ui_step(int id, int32_t v, int dir)
{
    const struct param_desc *d = &param_table[id];
    int32_t step;
    switch (d->unit) {
    case U_HZ:
    case U_HZ100:
    case U_MS:
    case U_Q100:
        step = v / 16; /* ~6 % per detent */
        if (step < 1)
            step = 1;
        break;
    default:
        step = (d->max - d->min) / 200;
        if (step < 1)
            step = 1;
    }
    return param_clamp(id, v + dir * step);
}

/* ---------------------------------------------------------------- drawing */
enum { PAL_BG, PAL_TITLE, PAL_TBG, PAL_VALUE, PAL_STATUS };
static const uint16_t palette[] = {C_BG, C_TITLE, C_TBG, C_VALUE, C_STATUS};
#define COL(fg, bg) ((uint8_t)((fg) << 4 | (bg)))

static void set_row(struct ui *u, int r, const char *text, uint8_t colours)
{
    for (int c = 0; c < UI_COLS; c++) {
        uint16_t cp = *text ? (uint16_t)utf8_next(&text) : ' ';
        struct ui_cell *e = &u->cell[r][c];
        if (e->cp != cp || e->colours != colours) {
            e->cp = cp;
            e->colours = colours;
            if (!e->dirty) {
                e->dirty = 1;
                u->ndirty++;
            }
        }
    }
}

void ui_poll(struct ui *u)
{
    for (int r = 0; r < UI_ROWS && u->ndirty; r++)
        for (int c = 0; c < UI_COLS; c++) {
            struct ui_cell *e = &u->cell[r][c];
            if (!e->dirty)
                continue;
            if (!disp_glyph(8 * c, ROW_Y(r), e->cp, palette[e->colours >> 4], palette[e->colours & 15]))
                return; /* no room: continue on the next call */
            e->dirty = 0;
            u->ndirty--;
        }
}

void ui_row_text(const struct ui *u, int r, char *buf, int n)
{
    int k = 0;
    for (int c = 0; c < UI_COLS && k + 4 < n; c++) {
        uint32_t cp = u->cell[r][c].cp;
        if (cp < 0x80) {
            buf[k++] = (char)cp;
        } else if (cp < 0x800) {
            buf[k++] = (char)(0xC0 | (cp >> 6));
            buf[k++] = (char)(0x80 | (cp & 0x3F));
        } else {
            buf[k++] = (char)(0xE0 | (cp >> 12));
            buf[k++] = (char)(0x80 | ((cp >> 6) & 0x3F));
            buf[k++] = (char)(0x80 | (cp & 0x3F));
        }
    }
    buf[k] = 0;
}

static void draw_param(struct ui *u, int slot)
{
    int id = pages[u->page].p[slot];
    char val[20], line[UI_COLS * 2 + 1];
    param_format(id, u->s->p.v[id], val, sizeof val);
    int pad = UI_COLS - 2 - utf8_len(param_table[id].label) - utf8_len(val);
    xsnprintf(line, sizeof line, "%d %s%*s%s", slot + 1, param_table[id].label, pad > 0 ? pad : 1, "", val);
    set_row(u, 2 + 2 * slot, line, COL(PAL_VALUE, PAL_BG));
}

static void draw_page(struct ui *u)
{
    char t[UI_COLS * 2 + 1];
    xsnprintf(t, sizeof t, "< %s  %d/%d >", pages[u->page].title, u->page + 1, ui_num_pages);
    set_row(u, 0, t, COL(PAL_TITLE, PAL_TBG));
    for (int k = 0; k < 3; k++)
        draw_param(u, k);
}

void ui_status(struct ui *u, const char *text) { set_row(u, 7, text, COL(PAL_STATUS, PAL_BG)); }

void ui_init(struct ui *u, struct synth *s)
{
    u->s = s;
    u->page = 0;
    u->status_until = 0;
    for (int k = 0; k < 4; k++)
        u->enc_prev[k] = 0;
    for (int k = 0; k < UI_POTS; k++)
        u->pot_last[k] = -1;
    /* the screen is black after disp_init: cells start as black spaces */
    for (int r = 0; r < UI_ROWS; r++)
        for (int c = 0; c < UI_COLS; c++)
            u->cell[r][c] = (struct ui_cell){' ', COL(PAL_BG, PAL_BG), 0};
    u->ndirty = 0;
    draw_page(u);
}

void ui_update(struct ui *u, const struct ui_input *in, uint32_t now_ms)
{
    int16_t d[4];
    for (int k = 0; k < 4; k++) {
        d[k] = (int16_t)(in->enc[k] - u->enc_prev[k]);
        u->enc_prev[k] = in->enc[k];
    }
    if (d[ENC_MENU] || (in->pressed & 1)) {
        int p = (in->pressed & 1) ? 0 : u->page + d[ENC_MENU];
        u->page = ((p % ui_num_pages) + ui_num_pages) % ui_num_pages;
        draw_page(u);
    }
    for (int k = 0; k < 3; k++) {
        if (!d[ENC_PAR1 + k])
            continue;
        int id = pages[u->page].p[k];
        int32_t v = u->s->p.v[id];
        for (int n = d[ENC_PAR1 + k]; n; n += n > 0 ? -1 : 1)
            v = ui_step(id, v, n > 0 ? 1 : -1);
        synth_set_param(u->s, id, v);
        draw_param(u, k);
    }
    for (int k = 0; k < UI_POTS; k++) {
        int raw = in->pot[k];
        int diff = raw - u->pot_last[k];
        if (u->pot_last[k] >= 0 && diff > -3 && diff < 3) /* hysteresis: 3 LSB of 12 bits */
            continue;
        int first = u->pot_last[k] < 0;
        u->pot_last[k] = (int16_t)raw;
        if (first)
            continue; /* a knob takes over its parameter when it is moved (presets stay) */
        int id = pots[k].param;
        synth_set_param(u->s, id, ui_pot_value(k, raw));
        char val[20], line[UI_COLS * 2 + 1];
        param_format(id, u->s->p.v[id], val, sizeof val);
        xsnprintf(line, sizeof line, "%s: %s", param_table[id].label, val);
        ui_status(u, line);
        u->status_until = now_ms + 1500;
        for (int s = 0; s < 3; s++) /* the same parameter may be on the page */
            if (pages[u->page].p[s] == id)
                draw_param(u, s);
    }
    if (u->status_until && (int32_t)(now_ms - u->status_until) > 0) {
        u->status_until = 0;
        ui_status(u, "");
    }
}
