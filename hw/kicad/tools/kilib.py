"""Чтение символов из библиотек KiCad: плоское определение (без extends) и выводы."""
import os
from sexp import parse, find, get, Sym  # noqa: F401

LIBDIR = os.environ.get('KICAD_SYMBOL_DIR', '/usr/share/kicad/symbols')
_cache = {}


def _lib(name, path=None):
    if name not in _cache:
        p = path or os.path.join(LIBDIR, name + '.kicad_sym')
        _cache[name] = parse(open(p, encoding='utf-8').read())[0]
    return _cache[name]


def raw_symbol(libname, sym, path=None):
    lib = _lib(libname, path)
    for s in find(lib, 'symbol'):
        if s[1] == sym:
            return s
    raise KeyError(f'{libname}:{sym}')


def flat_symbol(libname, sym, path=None):
    """Определение символа с подставленным родителем (extends) и именем lib:sym."""
    s = raw_symbol(libname, sym, path)
    ext = get(s, 'extends')
    if ext:
        parent = flat_symbol(libname, ext[1], path)
        body = [e for e in parent[2:] if not (isinstance(e, list) and e[0] == 'property')]
        props = [e for e in s[2:] if isinstance(e, list) and e[0] == 'property']
        other = [e for e in s[2:] if isinstance(e, list) and e[0] not in ('property', 'extends')]
        # подсимволы родителя переименовать
        out = [Sym('symbol'), sym] + other + props
        for e in body:
            if isinstance(e, list) and e[0] == 'symbol':
                e = list(e)
                e[1] = e[1].replace(ext[1] + '_', sym + '_', 1)
            out.append(e)
        s = out
    s = list(s)
    s[1] = f'{libname}:{sym}'
    return s


def pins(flat):
    """[(unit, number, name, x, y, angle, length, etype)] — координаты библиотеки (Y вверх)."""
    res = []
    base = flat[1].split(':')[-1]
    for sub in find(flat, 'symbol'):
        nm = sub[1]
        unit = int(nm.rsplit('_', 2)[-2])
        for p in find(sub, 'pin'):
            at = get(p, 'at')
            ln = get(p, 'length')
            name = get(p, 'name')[1]
            num = get(p, 'number')[1]
            res.append((unit, num, name, float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0,
                        float(ln[1]) if ln else 0.0, str(p[1])))
    return res


def units(flat):
    return sorted({p[0] for p in pins(flat)} - {0}) or [1]
