#include "console.h"

#include "hw.h"
#include "lib.h"

static struct synth *syn;
static struct ui *ui;
static char line[64];
static int len;

void console_init(struct synth *s, struct ui *u)
{
    syn = s;
    ui = u;
    len = 0;
}

static int split(char *s, char *argv[], int max)
{
    int n = 0;
    while (*s && n < max) {
        while (*s == ' ')
            *s++ = 0;
        if (!*s)
            break;
        argv[n++] = s;
        while (*s && *s != ' ')
            s++;
    }
    return n;
}

static int parse_int(const char *s, int32_t *v)
{
    int neg = 0;
    int32_t r = 0;
    if (*s == '-' || *s == '+')
        neg = *s++ == '-';
    if (!*s)
        return 0;
    for (; *s; s++) {
        if (*s < '0' || *s > '9')
            return 0;
        r = r * 10 + (*s - '0');
    }
    *v = neg ? -r : r;
    return 1;
}

static void show(int id)
{
    char buf[24];
    param_format(id, syn->p.v[id], buf, sizeof buf);
    log_printf("%s = %d (%s)\n", param_table[id].name, (int)syn->p.v[id], buf);
}

void console_exec(char *l)
{
    char *argv[6];
    int32_t a[5];
    int argc = split(l, argv, 6);
    if (argc == 0)
        return;
    const char *cmd = argv[0];
    if (!strcmp(cmd, "set") && argc == 3) {
        int id = param_find(argv[1]);
        if (id < 0 || !parse_int(argv[2], &a[0])) {
            log_printf("error: set <param> <int>\n");
            return;
        }
        synth_set_param(syn, id, a[0]);
        log_printf("ok ");
        show(id);
    } else if (!strcmp(cmd, "get") && argc == 2) {
        int id = param_find(argv[1]);
        if (id < 0)
            log_printf("error: unknown param\n");
        else
            show(id);
    } else if (!strcmp(cmd, "list")) {
        for (int i = 0; i < P_COUNT; i++)
            show(i);
    } else if (!strcmp(cmd, "route") && argc == 6) {
        for (int i = 0; i < 5; i++)
            if (!parse_int(argv[i + 1], &a[i])) {
                log_printf("error: route <k> <src> <via> <dst> <depth>\n");
                return;
            }
        if (a[0] < 1 || a[0] >= MOD_ROUTES) {
            log_printf("error: route 1..7 (0 is vibrato)\n");
            return;
        }
        synth_set_route(syn, a[0], (struct mod_route){(uint8_t)a[1], (uint8_t)a[2], (uint8_t)a[3], a[4]});
        log_printf("ok route %d\n", (int)a[0]);
    } else if (!strcmp(cmd, "note") && (argc == 2 || argc == 3) && parse_int(argv[1], &a[0])) {
        if (argc == 2 || !parse_int(argv[2], &a[1]))
            a[1] = 100;
        int v = synth_midi(syn, 0x90, (uint8_t)(a[0] & 127), (uint8_t)(a[1] & 127));
        log_printf("ok note %d v=%d\n", (int)a[0], v);
    } else if (!strcmp(cmd, "off") && argc == 2 && parse_int(argv[1], &a[0])) {
        synth_midi(syn, 0x80, (uint8_t)(a[0] & 127), 64);
        log_printf("ok off %d\n", (int)a[0]);
    } else if (!strcmp(cmd, "panel")) {
        log_printf("enc");
        for (int k = 0; k < 4; k++)
            log_printf(" %d", (int)(int16_t)hw_read(PERIPH_ADDR(7, 4u * k)));
        log_printf(" buttons %x pots", (unsigned)hw_read(PERIPH_ADDR(7, 0x10)));
        for (int k = 0; k < 8; k++)
            log_printf(" %u", (unsigned)(hw_read(PERIPH_ADDR(6, 4u * k)) >> 4));
        log_printf("\n");
    } else if (!strcmp(cmd, "avk")) {
        uint32_t hz = avk_sync_hz100(syn);
        for (int i = 0; i < 2; i++)
            log_printf("in%d raw %u val %d ", i + 1, (unsigned)hw_read(ADC_RAW(i)), (int)hw_read(ADC_IN(i)));
        log_printf("sync %u.%02u Hz edges %u\nbus", (unsigned)(hz / 100), (unsigned)(hz % 100),
                   (unsigned)hw_read(PERIPH_ADDR(9, 0x08)));
        for (int i = 0; i < BUS_SLOT0 + syn->nslots; i++)
            log_printf(" %d", (int)hw_read(BUS_VALUE(i)));
        log_printf("\n");
    } else if (!strcmp(cmd, "cal") && argc == 3 && parse_int(argv[1], &a[0]) && (a[0] == 1 || a[0] == 2)) {
        int i = (int)a[0] - 1;
        if (!strcmp(argv[2], "zero")) {
            avk_cal_zero(i);
        } else if (!parse_int(argv[2], &a[1]) || !avk_cal_ref(i, a[1])) {
            log_printf("error: cal <1|2> zero | cal <1|2> <mV> (after zero)\n");
            return;
        }
        log_printf("ok cal in%d offset %u gain %u\n", i + 1, (unsigned)hw_read(ADC_OFFSET(i)),
                   (unsigned)hw_read(ADC_GAIN(i)));
    } else if (!strcmp(cmd, "mem") && (argc == 2 || argc == 3) && parse_int(argv[1], &a[0])) {
        uint32_t addr = XRAM_BASE + 4u * (uint32_t)a[0]; /* word index in the external memory */
        if (argc == 3) {
            if (!parse_int(argv[2], &a[1])) {
                log_printf("error: mem <word> [value]\n");
                return;
            }
            hw_write(addr, (uint32_t)a[1]);
        }
        log_printf("ok mem %d = %d\n", (int)a[0], (int)hw_read(addr));
    } else if (!strcmp(cmd, "screen") && ui) {
        char row[UI_COLS * 3 + 1];
        for (int r = 0; r < UI_ROWS; r++) {
            ui_row_text(ui, r, row, sizeof row);
            log_printf("screen %d |%s|\n", r, row);
        }
        log_printf("screen end\n");
    } else if (!strcmp(cmd, "help")) {
        log_printf("set <param> <v> | get <param> | list | route <k> <src> <via> <dst> <depth> | "
                   "note <n> [vel] | off <n> | screen | avk | cal <1|2> zero|<mV> | mem <word> [value]\n");
    } else {
        log_printf("error: unknown command, try help\n");
    }
}

void console_feed(char c)
{
    if (c == '\r' || c == '\n') {
        line[len] = 0;
        len = 0;
        console_exec(line);
    } else if (len < (int)sizeof line - 1) {
        line[len++] = c;
    }
}
