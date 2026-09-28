/* Panel UI: menu pages of three parameters (encoders PAR1..PAR3), page selection (encoder MENU),
 * eight fixed potentiometers (a knob takes over its parameter once moved), a status line. Draws through disp.h; inputs are passed in,
 * so the logic runs on the host in tests. */
#ifndef UI_H
#define UI_H

#include <stdint.h>

#include "synth.h"

#define UI_COLS 30
#define UI_ROWS 8
#define UI_POTS 8

enum { ENC_MENU, ENC_PAR1, ENC_PAR2, ENC_PAR3 };

struct ui_input {
    int16_t enc[4];          /* detent counters (free running) */
    uint8_t pressed;         /* button press events, bit per encoder */
    uint16_t pot[UI_POTS];   /* 12-bit */
};

struct ui_cell {
    uint16_t cp;     /* code point */
    uint8_t colours; /* fg << 4 | bg, indices into the UI palette */
    uint8_t dirty;
};

struct ui {
    struct synth *s;
    int page;
    int16_t enc_prev[4];       /* last counter values: set to the hardware counters after ui_init */
    int16_t pot_last[UI_POTS]; /* -1: not seen yet */
    uint32_t status_until;     /* ms: pot popup shown until then */
    struct ui_cell cell[UI_ROWS][UI_COLS];
    int ndirty;
};

extern const int ui_num_pages;

void ui_init(struct ui *u, struct synth *s);
void ui_update(struct ui *u, const struct ui_input *in, uint32_t now_ms);
void ui_status(struct ui *u, const char *text);
void ui_poll(struct ui *u);                             /* draw changed cells, never waits */
void ui_row_text(const struct ui *u, int r, char *buf, int n); /* UTF-8 text of a row */
/* parameter change for one encoder detent (multiplicative for Hz / ms / Q) */
int32_t ui_step(int id, int32_t v, int dir);
/* potentiometer position (0..4095) -> parameter value */
int32_t ui_pot_value(int pot, int raw);
int ui_pot_param(int pot);

#endif
