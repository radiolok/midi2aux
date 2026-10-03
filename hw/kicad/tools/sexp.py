"""Минимальный разбор/печать S-выражений KiCad."""
import re

_tok = re.compile(r'\s*(?:(\()|(\))|("(?:[^"\\]|\\.)*")|([^\s()"]+))')


class Sym(str):
    """Неквотированный атом."""


def parse(text):
    pos, stack, cur = 0, [], []
    while True:
        m = _tok.match(text, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        if m.group(1):
            stack.append(cur)
            cur = []
        elif m.group(2):
            done = cur
            cur = stack.pop()
            cur.append(done)
        elif m.group(3) is not None:
            cur.append(m.group(3)[1:-1].replace('\\"', '"').replace('\\\\', '\\'))
        else:
            cur.append(Sym(m.group(4)))
    return cur


def q(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def dump(x, ind=0):
    if isinstance(x, list):
        if not x:
            return '()'
        simple = all(not isinstance(e, list) for e in x)
        if simple or len(x) <= 3 and sum(isinstance(e, list) for e in x) <= 1 and len(str(x)) < 80:
            return '(' + ' '.join(dump(e, ind) for e in x) + ')'
        head = []
        rest = list(x)
        while rest and not isinstance(rest[0], list):
            head.append(dump(rest.pop(0), ind))
        sp = '  ' * (ind + 1)
        return '(' + ' '.join(head) + ''.join('\n' + sp + dump(e, ind + 1) for e in rest) + ')'
    if isinstance(x, Sym):
        return str(x)
    if isinstance(x, (int, float)):
        return fmt(x)
    return q(x)


def fmt(v):
    if isinstance(v, int):
        return str(v)
    s = f'{v:.4f}'.rstrip('0').rstrip('.')
    return s if s not in ('-0', '') else '0'


def find(lst, key):
    return [e for e in lst if isinstance(e, list) and e and e[0] == key]


def get(lst, key):
    r = find(lst, key)
    return r[0] if r else None
