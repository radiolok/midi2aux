#!/usr/bin/env python3
"""Worst-case cycle count of an AVR ISR from avr-objdump -d output.

Walks the ISR from its label to reti; conditional branches are assumed
NOT taken (in the poly ISR that is the "voice active" path), rjmp/jmp are
followed. Adds 4 cycles interrupt response + 3 cycles vector-table jmp.

usage: isrcycles.py firmware.elf [vector_name] [take=ADDR,...]
  take=ADDR  treat the conditional branch at hex ADDR as taken
"""
import re, subprocess, sys

CYC = {'lds': 2, 'sts': 2, 'push': 2, 'pop': 2, 'ld': 2, 'ldd': 2, 'st': 2,
       'std': 2, 'rjmp': 2, 'jmp': 3, 'rcall': 3, 'call': 4, 'ret': 4,
       'reti': 4, 'lpm': 3, 'mul': 2, 'muls': 2, 'mulsu': 2, 'adiw': 2,
       'sbiw': 2, 'cbi': 2, 'sbi': 2}
BRANCH = re.compile(r'^br')

elf = sys.argv[1]
args = [a for a in sys.argv[2:] if not a.startswith('take=')]
vec = args[0] if args else '__vector_14'
take = set()
for a in sys.argv[2:]:
    if a.startswith('take='):
        take |= {int(x, 16) for x in a[5:].split(',') if x}
dis = subprocess.run(['avr-objdump', '-d', elf], capture_output=True, text=True).stdout
body = dis.split('<%s>:' % vec)[1]
ins = {}
for line in body.splitlines():
    m = re.match(r'\s*([0-9a-f]+):\s+(?:[0-9a-f]{2} )+\s*(\w+)\s*(.*)', line)
    if m:
        ins[int(m.group(1), 16)] = (m.group(2), m.group(3))
    if 'reti' in line:
        break
addrs = sorted(ins)
pc, total, n = addrs[0], 7, 0
while True:
    op, arg = ins[pc]
    taken = BRANCH.match(op) and pc in take
    total += (2 if taken else 1) if BRANCH.match(op) else CYC.get(op, 1)
    n += 1
    if op == 'reti':
        break
    if op in ('rjmp', 'jmp') or taken:
        pc = int(re.search(r'0x([0-9a-f]+)', arg.split(';')[-1]).group(1), 16)
    else:
        pc = addrs[addrs.index(pc) + 1]
print('%s: %d instructions on path, %d cycles (incl. 7 entry), size %d bytes'
      % (vec, n, total, max(addrs) + 2 - addrs[0]))
