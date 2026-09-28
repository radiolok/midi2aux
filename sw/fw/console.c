#include "console.h"

#include "lib.h"

static struct synth *syn;
static char line[64];
static int len;

void console_init(struct synth *s)
{
    syn = s;
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
    } else if (!strcmp(cmd, "help")) {
        log_printf("set <param> <v> | get <param> | list | route <k> <src> <via> <dst> <depth> | "
                   "note <n> [vel] | off <n>\n");
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
