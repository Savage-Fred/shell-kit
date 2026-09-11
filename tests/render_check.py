#!/usr/bin/env python3
"""Readable reference output on a light terminal, at screenshot-sized widths."""
import re
import subprocess as sp
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source='# Reference\n\n**F1** toggle help\n\n`Ctrl-b ← ↓ ↑ →` focus pane\n\n```sh\nrg -n "needle" file\n```\n'
for theme in ('light','dark'):
    result=sp.run([str(ROOT/'.venv/bin/python'),str(ROOT/'bin/render-sheet'),'60',theme],input=source,text=True,capture_output=True)
    assert result.returncode == 0, 'Markdown renderer missing: source highlighting is not rendered help'
    plain=re.sub(r'\x1b\[[0-9;]*m','',result.stdout)
    assert '**F1**' not in plain and '`Ctrl-b' not in plain and '# Reference' not in plain
    assert 'focus pane' in plain and 'toggle help' in plain and 'rg -n' in plain
    assert all(len(line)<=60 for line in plain.splitlines()), 'renderer exceeded pane width'
    assert ('\x1b[1;34m' if theme == 'light' else '\x1b[1;36m') in result.stdout, 'wrong shortcut colors for terminal theme'
    assert '\x1b[0m focus pane' in result.stdout, 'description must inherit terminal foreground'
print('PASS: rendered Markdown, syntax colors and width on light/dark terminals')
