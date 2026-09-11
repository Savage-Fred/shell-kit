#!/usr/bin/env python3
"""Install additive integrations. Back up edits; --dry-run changes nothing."""
import argparse
import datetime
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dry-run', action='store_true')
parser.add_argument('--uninstall', action='store_true')
args = parser.parse_args()
backup = HOME / '.local/state/shell-kit/backups' / datetime.datetime.now().strftime('%Y%m%dT%H%M%S%f')

def save(path):
    if path.exists():
        dest = backup / path.relative_to(HOME)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)

def block(path, body, marker='#'):
    start, end = marker + ' BEGIN SHELL-KIT', marker + ' END SHELL-KIT'
    old = path.read_text() if path.exists() else ''
    if start in old:
        first, tail = old.split(start, 1)
        if end not in tail:
            raise SystemExit('Malformed managed block: ' + str(path))
        old_clean = first + tail.split(end, 1)[1].lstrip('\n')
    else:
        old_clean = old
    new = old_clean.rstrip() + '\n'
    if not args.uninstall:
        new += '\n' + start + '\n' + body + '\n' + end + '\n'
    if new == old or (args.uninstall and start not in old):
        return
    print(('Would update ' if args.dry_run else 'Update ') + str(path))
    if not args.dry_run:
        save(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new)

def link(path, source):
    if path.is_symlink() and path.resolve() == source.resolve():
        if args.uninstall and not args.dry_run:
            path.unlink()
        return
    if args.uninstall:
        return
    if path.exists() or path.is_symlink():
        raise SystemExit('Refusing to replace existing path: ' + str(path))
    print(('Would link ' if args.dry_run else 'Link ') + str(path))
    if not args.dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(source)

if not args.uninstall:
    missing = [c for c in ('python3', 'tmux', 'less', 'rg', 'fzf') if not shutil.which(c)]
    if not (shutil.which('bat') or shutil.which('batcat')):
        missing.append('bat')
    if missing:
        raise SystemExit('Missing dependencies: ' + ', '.join(missing) + '. See README.')
link(HOME / '.local/share/shell-kit', ROOT)
for rc in ('.bashrc', '.zshrc'):
    block(HOME / rc, '[ -r "$HOME/.local/share/shell-kit/integrations/shell.sh" ] && . "$HOME/.local/share/shell-kit/integrations/shell.sh"')
block(HOME / '.tmux.conf', 'source-file -q ~/.local/share/shell-kit/integrations/tmux.conf')
vim_body = '''" Disable the old automatic sidebar, preserving its source for rollback.
augroup CheatsheetAuto
  autocmd!
augroup END
source ~/.local/share/shell-kit/integrations/vim.vim'''
block(HOME / '.vimrc', vim_body, '"')
nvim = HOME / '.config/nvim'
if (nvim / 'init.lua').exists():
    block(nvim / 'init.lua', "vim.cmd('source ~/.local/share/shell-kit/integrations/vim.vim')", '--')
else:
    block(nvim / 'init.vim', vim_body, '"')
for base in ('.agents/skills', '.codex/skills', '.claude/skills', '.gemini/skills', '.gemini/antigravity/skills'):
    link(HOME / base / 'tmux-reference', ROOT / 'skills/tmux-reference')
if not args.dry_run and not args.uninstall:
    runtime = HOME / '.local/share/shell-kit-runtime/bin'
    runtime.mkdir(parents=True, exist_ok=True)
    for name in ('tmux', 'less', 'rg', 'fzf', 'bat', 'batcat'):
        found = shutil.which(name)
        path = runtime / name
        if found and not path.exists():
            path.symlink_to(found)
    config = HOME / '.config/shell-kit/clients.json'
    if not config.exists():
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('{}\n')
print('Backups: ' + str(backup))
print('Open a new shell. Existing tmux servers: tmux source-file ~/.tmux.conf')
