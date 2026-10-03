#!/usr/bin/env python3
"""Проверка схемы: kicad-cli → netlist, сравнение с задуманными цепями, повторы обозначений,
цепи из одного вывода. Запуск: python3 hw/kicad/tools/check.py"""
import os
import subprocess
import sys
import tempfile
from collections import defaultdict, Counter

sys.path.insert(0, os.path.dirname(__file__))
from sexp import parse, find, get  # noqa: E402
import gen_kicad as g  # noqa: E402

KDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def main():
    with tempfile.TemporaryDirectory() as td:
        net = os.path.join(td, 'n.net')
        r = subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadsexpr', '-o', net,
                            os.path.join(KDIR, 'avk_synth.kicad_sch')], capture_output=True, text=True)
        out = r.stdout + r.stderr
        if 'annotation' in out.lower() or r.returncode:
            print(out)
        doc = parse(open(net, encoding='utf-8').read())[0]
    got = {}
    for n in find(get(doc, 'nets'), 'net'):
        name = get(n, 'name')[1]
        nodes = frozenset(f'{get(x, "ref")[1]}.{get(x, "pin")[1]}' for x in find(n, 'node'))
        got[nodes] = name
    exp = defaultdict(set)
    refs = Counter()
    for sh in g.SHEETS.values():
        for _, parts in sh['groups']:
            seen = set()
            for p in parts:
                for num, netn in p.pins.items():
                    if netn != g.NC and not p.ref.startswith('#'):
                        exp[netn].add(f'{p.ref}.{num}')
                if not p.ref.startswith('#'):
                    refs[(p.ref, tuple(sorted(p.pins)))] += 1
    errors = 0
    # повторы обозначений с одинаковыми выводами (разные юниты — нормально)
    by_ref = defaultdict(list)
    for (ref, pins), c in refs.items():
        by_ref[ref].append(pins)
    for ref, lst in by_ref.items():
        allp = [x for t in lst for x in t]
        if len(allp) != len(set(allp)):
            print('ПОВТОР обозначения/вывода:', ref)
            errors += 1
    got_sets = set(got)
    for netn, nodes in sorted(exp.items()):
        fs = frozenset(nodes)
        if fs not in got_sets:
            # найти, с чем слилось / как разбилось
            hits = [(got[k], len(k)) for k in got if k & fs]
            print(f'НЕ СОВПАДАЕТ {netn}: ожидалось {len(fs)} выв., в KiCad: {hits}')
            errors += 1
        if len(nodes) == 1 and not netn.startswith(('5V_TN',)):
            print(f'ОДИН ВЫВОД в цепи {netn}: {next(iter(nodes))}')
    extra = [got[k] for k in got if not any(k == frozenset(v) for v in exp.values())
             and not got[k].startswith('unconnected-')]
    for e in extra:
        print('ЛИШНЯЯ цепь в KiCad:', e)
    print('цепей ожидалось:', len(exp), 'в netlist:', len(got), 'ошибок:', errors)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
