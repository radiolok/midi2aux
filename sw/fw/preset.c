#include "preset.h"

uint16_t preset_hash(const char *name)
{
    uint32_t h = 2166136261u; /* FNV-1a, folded to 16 bits */
    while (*name)
        h = (h ^ (uint8_t)*name++) * 16777619u;
    return (uint16_t)(h ^ (h >> 16));
}

static void put16(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static uint16_t get16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }

int preset_pack(const struct synth *s, uint8_t *buf)
{
    uint8_t *p = buf;
    *p++ = 'A', *p++ = 'V', *p++ = 'K', *p++ = 'P';
    put16(p, 1);
    put16(p + 2, P_COUNT);
    p += 4;
    for (int i = 0; i < P_COUNT; i++, p += 4) {
        put16(p, preset_hash(param_table[i].name));
        put16(p + 2, (uint32_t)s->p.v[i]);
    }
    for (int k = 1; k < MOD_ROUTES; k++, p += 8) {
        const struct mod_route *r = &s->routes[k];
        p[0] = r->src, p[1] = r->via, p[2] = r->dst, p[3] = 0;
        put16(p + 4, (uint32_t)r->depth);
        put16(p + 6, (uint32_t)r->depth >> 16);
    }
    return (int)(p - buf);
}

int preset_unpack(struct synth *s, const uint8_t *buf, int len)
{
    if (len < 8 || buf[0] != 'A' || buf[1] != 'V' || buf[2] != 'K' || buf[3] != 'P' || get16(buf + 4) != 1)
        return -1;
    int n = get16(buf + 6), used = 0;
    const uint8_t *p = buf + 8;
    if (8 + 4 * n > len)
        return -1;
    for (int k = 0; k < n; k++, p += 4) {
        uint16_t h = get16(p);
        for (int i = 0; i < P_COUNT; i++)
            if (preset_hash(param_table[i].name) == h) {
                s->p.v[i] = param_clamp(i, (int16_t)get16(p + 2));
                used++;
                break;
            }
    }
    if (p + 8 * (MOD_ROUTES - 1) <= buf + len)
        for (int k = 1; k < MOD_ROUTES; k++, p += 8)
            synth_set_route(s, k, (struct mod_route){p[0], p[1], p[2],
                                                     (int32_t)(get16(p + 4) | (uint32_t)get16(p + 6) << 16)});
    synth_apply_patch(s);
    return used;
}

void preset_name(int n, char out[13])
{
    const char *t = "PRESET00.BIN";
    for (int i = 0; i < 13; i++)
        out[i] = t[i];
    out[6] = (char)('0' + n / 10 % 10);
    out[7] = (char)('0' + n % 10);
}
