#include "voice_alloc.h"

static void mask_set(uint32_t m[2], int v) { m[v >> 5] |= 1u << (v & 31); }

void va_init(struct voice_alloc *a, int n, struct va_hw hw)
{
    a->n = n > VA_MAX_VOICES ? VA_MAX_VOICES : n;
    a->sustain = 0;
    a->clock = 0;
    a->hw = hw;
    for (int i = 0; i < VA_MAX_VOICES; i++) {
        a->v[i].note = VA_NO_NOTE;
        a->v[i].held = 0;
        a->v[i].sustained = 0;
        a->v[i].age = 0;
    }
}

int va_gated(const struct voice_alloc *a, int v) { return a->v[v].held || a->v[v].sustained; }

int va_note_on(struct voice_alloc *a, uint8_t note, int *retrig)
{
    int pick = -1;
    /* 1. the same note: reuse its voice */
    for (int i = 0; i < a->n; i++)
        if (a->v[i].note == note) {
            pick = i;
            break;
        }
    /* 2. a free voice: not gated and envelope idle; prefer the least recently used */
    if (pick < 0)
        for (int i = 0; i < a->n; i++)
            if (!va_gated(a, i) && a->hw.idle(a->hw.ctx, i) && (pick < 0 || a->v[i].age < a->v[pick].age))
                pick = i;
    /* 3. steal a releasing voice with the lowest level */
    if (pick < 0) {
        uint32_t best = 0xFFFFFFFFu;
        for (int i = 0; i < a->n; i++)
            if (!va_gated(a, i)) {
                uint32_t l = a->hw.level(a->hw.ctx, i);
                if (l < best) {
                    best = l;
                    pick = i;
                }
            }
    }
    /* 4. steal the oldest voice */
    if (pick < 0) {
        pick = 0;
        for (int i = 1; i < a->n; i++)
            if (a->v[i].age < a->v[pick].age)
                pick = i;
    }
    *retrig = va_gated(a, pick);
    struct va_voice *v = &a->v[pick];
    v->note = note;
    v->held = 1;
    v->sustained = 0;
    v->age = ++a->clock;
    return pick;
}

int va_note_off(struct voice_alloc *a, uint8_t note)
{
    for (int i = 0; i < a->n; i++) {
        struct va_voice *v = &a->v[i];
        if (v->note == note && v->held) {
            v->held = 0;
            if (a->sustain) {
                v->sustained = 1;
                return -1;
            }
            return i;
        }
    }
    return -1;
}

void va_sustain(struct voice_alloc *a, int on, uint32_t mask[2])
{
    mask[0] = mask[1] = 0;
    a->sustain = (uint8_t)(on != 0);
    if (on)
        return;
    for (int i = 0; i < a->n; i++)
        if (a->v[i].sustained) {
            a->v[i].sustained = 0;
            mask_set(mask, i);
        }
}

void va_all_off(struct voice_alloc *a, uint32_t mask[2])
{
    mask[0] = mask[1] = 0;
    for (int i = 0; i < a->n; i++) {
        if (va_gated(a, i))
            mask_set(mask, i);
        a->v[i].held = a->v[i].sustained = 0;
    }
}
