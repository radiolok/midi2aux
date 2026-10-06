#include "fat.h"

static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }
static uint32_t rd32(const uint8_t *p) { return (uint32_t)rd16(p) | (uint32_t)rd16(p + 2) << 16; }
static void wr16(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void wr32(uint8_t *p, uint32_t v) { wr16(p, v); wr16(p + 2, v >> 16); }

int fat_flush(struct fat *f)
{
    if (f->dirty) {
        if (f->dev.write(f->dev.ctx, f->buf_lba, f->buf))
            return FAT_EIO;
        f->dirty = 0;
    }
    return FAT_OK;
}

static uint8_t *sector(struct fat *f, uint32_t lba)
{
    if (lba == f->buf_lba)
        return f->buf;
    if (fat_flush(f))
        return 0;
    f->buf_lba = 0xFFFFFFFFu;
    if (f->dev.read(f->dev.ctx, lba, f->buf))
        return 0;
    f->buf_lba = lba;
    return f->buf;
}

int fat_mount(struct fat *f, struct blkdev dev)
{
    f->dev = dev;
    f->dirty = 0;
    f->buf_lba = 0xFFFFFFFFu;
    uint8_t *b = sector(f, 0);
    if (!b)
        return FAT_EIO;
    if (b[510] != 0x55 || b[511] != 0xAA)
        return FAT_ENOFS;
    uint32_t part = 0;
    uint8_t t = b[0x1C2];
    if (rd16(b + 11) != 512 && (t == 0x04 || t == 0x06 || t == 0x0B || t == 0x0C || t == 0x0E)) {
        part = rd32(b + 0x1C6);
        if (!(b = sector(f, part)))
            return FAT_EIO;
    }
    if (rd16(b + 11) != 512 || !b[13] || !b[16])
        return FAT_ENOFS;
    uint32_t rsv = rd16(b + 14), rootents = rd16(b + 17), tot = rd16(b + 19);
    f->spc = b[13];
    f->nfats = b[16];
    f->fatsz = rd16(b + 22);
    if (!tot)
        tot = rd32(b + 32);
    if (!f->fatsz)
        f->fatsz = rd32(b + 36);
    f->fat0 = part + rsv;
    f->root_secs = (rootents * 32 + 511) / 512;
    f->root0 = f->fat0 + f->nfats * f->fatsz;
    f->data0 = f->root0 + f->root_secs;
    f->nclus = (tot - rsv - f->nfats * f->fatsz - f->root_secs) / f->spc;
    f->fat32 = f->nclus >= 65525;
    if (f->nclus < 4085)
        return FAT_ENOFS; /* FAT12 */
    f->root_clus = f->fat32 ? rd32(b + 44) : 0;
    f->eoc = f->fat32 ? 0x0FFFFFF8u : 0xFFF8u;
    return FAT_OK;
}

static int fat_get(struct fat *f, uint32_t n, uint32_t *v)
{
    uint32_t off = n * (f->fat32 ? 4u : 2u);
    uint8_t *b = sector(f, f->fat0 + off / 512);
    if (!b)
        return FAT_EIO;
    *v = f->fat32 ? rd32(b + off % 512) & 0x0FFFFFFFu : rd16(b + off % 512);
    return FAT_OK;
}

static int fat_set(struct fat *f, uint32_t n, uint32_t v)
{
    uint32_t off = n * (f->fat32 ? 4u : 2u);
    for (uint32_t k = 0; k < f->nfats; k++) {
        uint8_t *b = sector(f, f->fat0 + k * f->fatsz + off / 512);
        if (!b)
            return FAT_EIO;
        if (f->fat32)
            wr32(b + off % 512, (rd32(b + off % 512) & 0xF0000000u) | (v & 0x0FFFFFFFu));
        else
            wr16(b + off % 512, v);
        f->dirty = 1;
    }
    return FAT_OK;
}

static uint32_t clus_lba(const struct fat *f, uint32_t c) { return f->data0 + (c - 2) * f->spc; }

/* lba of the i-th root directory sector, 0 past the end */
static uint32_t root_sector(struct fat *f, uint32_t i)
{
    if (!f->fat32)
        return i < f->root_secs ? f->root0 + i : 0;
    uint32_t c = f->root_clus;
    for (uint32_t k = i / f->spc; k; k--)
        if (fat_get(f, c, &c) || c < 2 || c >= f->eoc)
            return 0;
    return clus_lba(f, c) + i % f->spc;
}

static void to83(const char *name, uint8_t out[11])
{
    int i = 0;
    for (int k = 0; k < 11; k++)
        out[k] = ' ';
    for (; *name && *name != '.' && i < 8; name++)
        out[i++] = (uint8_t)(*name >= 'a' && *name <= 'z' ? *name - 32 : *name);
    while (*name && *name != '.')
        name++;
    if (*name == '.')
        name++;
    for (i = 8; *name && i < 11; name++)
        out[i++] = (uint8_t)(*name >= 'a' && *name <= 'z' ? *name - 32 : *name);
}

/* finds the entry (lba, offset); with free_* also the first free slot. 0 found, FAT_ENOENT not */
static int find(struct fat *f, const uint8_t n83[11], uint32_t *lba, uint32_t *off, uint32_t *free_lba,
                uint32_t *free_off)
{
    if (free_lba)
        *free_lba = 0;
    for (uint32_t i = 0;; i++) {
        uint32_t s = root_sector(f, i);
        if (!s)
            return FAT_ENOENT;
        uint8_t *b = sector(f, s);
        if (!b)
            return FAT_EIO;
        for (uint32_t o = 0; o < 512; o += 32) {
            uint8_t *e = b + o;
            if ((e[0] == 0 || e[0] == 0xE5) && free_lba && !*free_lba) {
                *free_lba = s;
                *free_off = o;
            }
            if (e[0] == 0)
                return FAT_ENOENT;
            if (e[0] == 0xE5 || e[11] == 0x0F || (e[11] & 0x18))
                continue;
            int eq = 1;
            for (int k = 0; k < 11; k++)
                eq &= e[k] == n83[k];
            if (eq) {
                *lba = s;
                *off = o;
                return FAT_OK;
            }
        }
    }
}

int fat_open(struct fat *f, const char *name, struct fat_file *file)
{
    uint8_t n83[11];
    uint32_t lba, off;
    to83(name, n83);
    int r = find(f, n83, &lba, &off, 0, 0);
    if (r)
        return r;
    uint8_t *e = sector(f, lba);
    if (!e)
        return FAT_EIO;
    e += off;
    file->first = file->clus = rd16(e + 26) | (uint32_t)rd16(e + 20) << 16;
    file->size = rd32(e + 28);
    file->pos = 0;
    return FAT_OK;
}

int32_t fat_fread(struct fat *f, struct fat_file *file, void *dst, uint32_t n)
{
    uint8_t *d = dst;
    uint32_t done = 0, csize = f->spc * 512;
    while (done < n && file->pos < file->size) {
        if (file->pos && file->pos % csize == 0 && (fat_get(f, file->clus, &file->clus)))
            return FAT_EIO;
        if (file->clus < 2 || file->clus >= f->eoc)
            return FAT_EIO;
        uint32_t in = file->pos % csize;
        uint8_t *b = sector(f, clus_lba(f, file->clus) + in / 512);
        if (!b)
            return FAT_EIO;
        uint32_t k = 512 - in % 512;
        if (k > n - done)
            k = n - done;
        if (k > file->size - file->pos)
            k = file->size - file->pos;
        for (uint32_t i = 0; i < k; i++)
            d[done + i] = b[in % 512 + i];
        done += k;
        file->pos += k;
    }
    return (int32_t)done;
}

int32_t fat_read(struct fat *f, const char *name, void *dst, uint32_t max)
{
    struct fat_file file;
    int r = fat_open(f, name, &file);
    if (r)
        return r;
    if (file.size > max)
        return FAT_EBIG;
    return fat_fread(f, &file, dst, file.size);
}

static int free_chain(struct fat *f, uint32_t c)
{
    while (c >= 2 && c < f->eoc) {
        uint32_t nx;
        if (fat_get(f, c, &nx) || fat_set(f, c, 0))
            return FAT_EIO;
        c = nx;
    }
    return FAT_OK;
}

int fat_write(struct fat *f, const char *name, const void *src, uint32_t len)
{
    uint8_t n83[11];
    uint32_t lba, off, flba, foff, first = 0, prev = 0, csize = f->spc * 512;
    const uint8_t *s = src;
    to83(name, n83);
    int r = find(f, n83, &lba, &off, &flba, &foff);
    if (r == FAT_OK) {
        uint8_t *e = sector(f, lba);
        if (!e || free_chain(f, rd16(e + off + 26) | (uint32_t)rd16(e + off + 20) << 16))
            return FAT_EIO;
    } else if (r == FAT_ENOENT && flba) {
        lba = flba;
        off = foff;
    } else {
        return r == FAT_ENOENT ? FAT_EFULL : r;
    }
    /* data: first-fit clusters, linked as they are written */
    uint32_t c = 2;
    for (uint32_t pos = 0; pos < len; pos += csize) {
        uint32_t v = 1;
        for (; c < f->nclus + 2; c++)
            if (fat_get(f, c, &v) || !v)
                break;
        if (v)
            return FAT_EFULL;
        for (uint32_t k = 0; k < f->spc; k++) {
            uint8_t *b = sector(f, clus_lba(f, c) + k);
            if (!b)
                return FAT_EIO;
            for (uint32_t i = 0; i < 512; i++) {
                uint32_t p = pos + k * 512 + i;
                b[i] = p < len ? s[p] : 0;
            }
            f->dirty = 1;
        }
        if (fat_set(f, c, 0x0FFFFFFFu) || (prev && fat_set(f, prev, c)))
            return FAT_EIO;
        if (!first)
            first = c;
        prev = c;
    }
    uint8_t *e = sector(f, lba);
    if (!e)
        return FAT_EIO;
    e += off;
    for (int k = 0; k < 32; k++)
        e[k] = k < 11 ? n83[k] : 0;
    e[11] = 0x20;
    wr16(e + 20, first >> 16);
    wr16(e + 26, first);
    wr32(e + 28, len);
    f->dirty = 1;
    return fat_flush(f);
}

int fat_list(struct fat *f, void (*cb)(void *ctx, const char *name, uint32_t size), void *ctx)
{
    for (uint32_t i = 0;; i++) {
        uint32_t s = root_sector(f, i);
        if (!s)
            return FAT_OK;
        for (uint32_t o = 0; o < 512; o += 32) {
            uint8_t *e = sector(f, s);
            if (!e)
                return FAT_EIO;
            e += o;
            if (e[0] == 0)
                return FAT_OK;
            if (e[0] == 0xE5 || e[11] == 0x0F || (e[11] & 0x18))
                continue;
            char name[13];
            int k = 0;
            for (int i2 = 0; i2 < 8 && e[i2] != ' '; i2++)
                name[k++] = (char)e[i2];
            if (e[8] != ' ') {
                name[k++] = '.';
                for (int i2 = 8; i2 < 11 && e[i2] != ' '; i2++)
                    name[k++] = (char)e[i2];
            }
            name[k] = 0;
            cb(ctx, name, rd32(e + 28));
        }
    }
}
