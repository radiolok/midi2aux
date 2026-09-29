#include "patch.h"

#include "lib.h"

static const char *const wave_names[] = {"saw", "square", "tri", "sine", 0};
static const char *const fmode_names[] = {"lp", "bp", "hp", 0};
static const char *const lfo_names[] = {"sine", "tri", "saw", "square", "random", "sawdn", 0};
static const char *const bus_names[] = {"synth", "in1", "in2", "lfo1", "lfo2", "sync", "env", "gate",
                                        "slot1", "slot2", "slot3", "slot4", "pitch", 0};
static const char *const hsync_names[] = {"off", "osc1", "osc2", "both", 0};
static const char *const in_names[] = {"in1", "in2", 0};
static const char *const onoff_names[] = {"off", "on", 0};
static const char *const op_names[] = {"off", "mul", "div", "abs", "add", "sub", "min", "max", "mod", "axpb", 0};
static const char *const sync_names[] = {"off", "lfo", "note", 0};

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
    [P_IN1_MIX]   = {"in1mix", "ВХ1 → ВЫХ", -200, 200, 0, U_PCT, 0},
    [P_IN2_MIX]   = {"in2mix", "ВХ2 → ВЫХ", -200, 200, 0, U_PCT, 0},
    [P_OUT2_SRC]  = {"out2src", "ВЫХ2 сигнал", 0, 12, 3, U_ENUM, bus_names},
    [P_OUT2_GAIN] = {"out2gain", "ВЫХ2 уровень", -200, 200, 100, U_PCT, 0},
    [P_SYNC_MODE] = {"syncmode", "SYNC режим", 0, 2, 0, U_ENUM, sync_names},
    [P_SYNC_NOTE] = {"syncnote", "SYNC нота", 0, 127, 60, U_NONE, 0},
    [P_SLOT1_OP]  = {"slot1op", "СЛОТ1 операция", 0, 9, 0, U_ENUM, op_names},
    [P_SLOT1_A]   = {"slot1a", "СЛОТ1 A", 0, 11, 1, U_ENUM, bus_names},
    [P_SLOT1_B]   = {"slot1b", "СЛОТ1 B", 0, 11, 2, U_ENUM, bus_names},
    [P_SLOT1_K]   = {"slot1k", "СЛОТ1 k", -200, 200, 100, U_PCT, 0},
    [P_SLOT2_OP]  = {"slot2op", "СЛОТ2 операция", 0, 9, 0, U_ENUM, op_names},
    [P_SLOT2_A]   = {"slot2a", "СЛОТ2 A", 0, 11, 1, U_ENUM, bus_names},
    [P_SLOT2_B]   = {"slot2b", "СЛОТ2 B", 0, 11, 2, U_ENUM, bus_names},
    [P_SLOT2_K]   = {"slot2k", "СЛОТ2 k", -200, 200, 100, U_PCT, 0},
    [P_DLY1_SRC]  = {"dly1src", "ЗАДЕРЖКА1 вход", 0, 11, 1, U_ENUM, bus_names},
    [P_DLY1_TIME] = {"dly1time", "ЗАДЕРЖКА1 время", 1, 20000, 250, U_MS, 0},
    [P_DLY1_FB]   = {"dly1fb", "ЗАДЕРЖКА1 повтор", -99, 99, 40, U_PCT, 0},
    [P_DLY1_LVL]  = {"dly1lvl", "ЗАДЕРЖКА1 уровень", -200, 200, 0, U_PCT, 0},
    [P_DLY2_SRC]  = {"dly2src", "ЗАДЕРЖКА2 вход", 0, 11, 2, U_ENUM, bus_names},
    [P_DLY2_TIME] = {"dly2time", "ЗАДЕРЖКА2 время", 1, 20000, 375, U_MS, 0},
    [P_DLY2_FB]   = {"dly2fb", "ЗАДЕРЖКА2 повтор", -99, 99, 40, U_PCT, 0},
    [P_DLY2_LVL]  = {"dly2lvl", "ЗАДЕРЖКА2 уровень", -200, 200, 0, U_PCT, 0},
    [P_DLY_SYNC]  = {"dlysync", "Задержка = СИНХР", 0, 1, 0, U_ENUM, onoff_names},
    [P_CHO_SRC]   = {"chosrc", "ХОРУС вход", 0, 11, 0, U_ENUM, bus_names},
    [P_CHO_BASE]  = {"chobase", "ХОРУС задержка", 1, 200, 70, U_MS10, 0},
    [P_CHO_DEPTH] = {"chodepth", "ХОРУС глубина", 0, 200, 30, U_MS10, 0},
    [P_CHO_RATE]  = {"chorate", "ХОРУС частота", 1, 1000, 50, U_HZ100, 0},
    [P_CHO_FB]    = {"chofb", "ХОРУС повтор", -99, 99, 0, U_PCT, 0},
    [P_CHO_LVL]   = {"cholvl", "ХОРУС уровень", -200, 200, 0, U_PCT, 0},
    [P_REV_SRC]   = {"revsrc", "РЕВЕРБ. вход", 0, 11, 0, U_ENUM, bus_names},
    [P_REV_ROOM]  = {"revroom", "РЕВЕРБ. размер", 0, 100, 50, U_PCT, 0},
    [P_REV_DAMP]  = {"revdamp", "РЕВЕРБ. глушение", 0, 100, 50, U_PCT, 0},
    [P_REV_LVL]   = {"revlvl", "РЕВЕРБ. уровень", -200, 200, 0, U_PCT, 0},
    [P_HSYNC]     = {"hsync", "Жёсткая синхр.", 0, 3, 0, U_ENUM, hsync_names},
    [P_FOLLOW_SRC] = {"follsrc", "Детектор вход", 0, 1, 0, U_ENUM, in_names},
    [P_FOLLOW_ATK] = {"follatk", "Детектор атака", 1, 1000, 5, U_MS, 0},
    [P_FOLLOW_REL] = {"follrel", "Детектор спад", 1, 5000, 100, U_MS, 0},
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
    case U_MS10:
        xsnprintf(buf, (size_t)n, "%d.%d ms", (int)(v / 10), (int)(v % 10));
        break;
    case U_Q100:
        xsnprintf(buf, (size_t)n, "%d.%02d", (int)(v / 100), (int)(v % 100));
        break;
    default:
        xsnprintf(buf, (size_t)n, "%d", (int)v);
    }
}
