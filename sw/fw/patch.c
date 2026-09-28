#include "patch.h"

#include "lib.h"

static const char *const wave_names[] = {"saw", "square", "tri", "sine", 0};
static const char *const fmode_names[] = {"lp", "bp", "hp", 0};
static const char *const lfo_names[] = {"sine", "tri", "saw", "square", "random", "sawdn", 0};

const struct param_desc param_table[P_COUNT] = {
    [P_WAVE1]     = {"wave1", "ГЕН1 форма", 0, 3, 0, U_ENUM, wave_names},
    [P_WAVE2]     = {"wave2", "ГЕН2 форма", 0, 3, 0, U_ENUM, wave_names},
    [P_PW]        = {"pw", "Скважность", 1, 99, 50, U_PCT, 0},
    [P_DETUNE]    = {"detune", "ГЕН2 расстр.", -100, 100, 7, U_CENTS, 0},
    [P_OSC2_SEMI] = {"osc2semi", "ГЕН2 полутон", -12, 12, 0, U_SEMI, 0},
    [P_MIX1]      = {"mix1", "Уровень ГЕН1", 0, 100, 50, U_PCT, 0},
    [P_MIX2]      = {"mix2", "Уровень ГЕН2", 0, 100, 50, U_PCT, 0},
    [P_NOISE]     = {"noise", "Шум", 0, 100, 0, U_PCT, 0},
    [P_CUTOFF]    = {"cutoff", "Срез", 20, 16000, 4000, U_HZ, 0},
    [P_RES]       = {"res", "Резонанс Q", 50, 2000, 100, U_Q100, 0},
    [P_FMODE]     = {"fmode", "Фильтр", 0, 2, 0, U_ENUM, fmode_names},
    [P_ENV2_AMT]  = {"env2amt", "ENV→Ф", -4800, 4800, 2400, U_CENTS, 0},
    [P_VEL_CUT]   = {"velcut", "Сила→Ф", -4800, 4800, 1200, U_CENTS, 0},
    [P_VEL_AMP]   = {"velamp", "Сила→громк.", 0, 100, 75, U_PCT, 0},
    [P_A1]        = {"a1", "A1", 1, 10000, 5, U_MS, 0},
    [P_D1]        = {"d1", "D1", 1, 10000, 300, U_MS, 0},
    [P_S1]        = {"s1", "S1", 0, 100, 70, U_PCT, 0},
    [P_R1]        = {"r1", "R1", 1, 10000, 300, U_MS, 0},
    [P_A2]        = {"a2", "A2", 1, 10000, 5, U_MS, 0},
    [P_D2]        = {"d2", "D2", 1, 10000, 500, U_MS, 0},
    [P_S2]        = {"s2", "S2", 0, 100, 30, U_PCT, 0},
    [P_R2]        = {"r2", "R2", 1, 10000, 300, U_MS, 0},
    [P_LFO1_RATE] = {"lfo1rate", "LFO1 частота", 1, 5000, 550, U_HZ100, 0},
    [P_LFO1_WAVE] = {"lfo1wave", "LFO1 форма", 0, 5, 0, U_ENUM, lfo_names},
    [P_LFO2_RATE] = {"lfo2rate", "LFO2 частота", 1, 5000, 30, U_HZ100, 0},
    [P_LFO2_WAVE] = {"lfo2wave", "LFO2 форма", 0, 5, 1, U_ENUM, lfo_names},
    [P_VIBRATO]   = {"vibrato", "Вибрато", 0, 1200, 50, U_CENTS, 0},
    [P_BEND]      = {"bend", "Диап. bend", 0, 24, 2, U_SEMI, 0},
    [P_MASTER]    = {"master", "Уровень", 0, 200, 25, U_PCT, 0},
    [P_FX_MIX]    = {"fxmix", "FX MIX", 0, 100, 50, U_PCT, 0},
};

void patch_defaults(struct patch *p)
{
    for (int i = 0; i < P_COUNT; i++)
        p->v[i] = param_table[i].def;
}

int param_find(const char *name)
{
    for (int i = 0; i < P_COUNT; i++)
        if (!strcmp(param_table[i].name, name))
            return i;
    return -1;
}

int32_t param_clamp(int id, int32_t v)
{
    const struct param_desc *d = &param_table[id];
    return v < d->min ? d->min : v > d->max ? d->max : v;
}

void param_format(int id, int32_t v, char *buf, int n)
{
    const struct param_desc *d = &param_table[id];
    switch (d->unit) {
    case U_ENUM:
        xsnprintf(buf, (size_t)n, "%s", d->enum_names[v]);
        break;
    case U_HZ:
        xsnprintf(buf, (size_t)n, "%d Hz", (int)v);
        break;
    case U_HZ100:
        xsnprintf(buf, (size_t)n, "%d.%02d Hz", (int)(v / 100), (int)(v % 100));
        break;
    case U_MS:
        xsnprintf(buf, (size_t)n, "%d ms", (int)v);
        break;
    case U_PCT:
        xsnprintf(buf, (size_t)n, "%d %%", (int)v);
        break;
    case U_CENTS:
        xsnprintf(buf, (size_t)n, "%d ct", (int)v);
        break;
    case U_SEMI:
        xsnprintf(buf, (size_t)n, "%d st", (int)v);
        break;
    case U_Q100:
        xsnprintf(buf, (size_t)n, "%d.%02d", (int)(v / 100), (int)(v % 100));
        break;
    default:
        xsnprintf(buf, (size_t)n, "%d", (int)v);
    }
}
