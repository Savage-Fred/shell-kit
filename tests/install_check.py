#!/usr/bin/env python3
"""Exercise component installation with synthetic configs and a minimal PATH."""
import os
from pathlib import Path
import shutil
import subprocess as sp
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASH = os.environ.get('SHELL_KIT_TEST_BASH', '/bin/bash')
assert (ROOT / 'install.sh').exists(), 'Bash component installer is missing'

with tempfile.TemporaryDirectory(prefix='shell-kit-install-') as folder:
    home = Path(folder) / 'home with spaces'
    home.mkdir()
    minimal = Path(folder) / 'bin'
    minimal.mkdir()
    for name in ('bash', 'awk', 'cat', 'cmp', 'cp', 'dirname', 'ln', 'mkdir',
                 'mktemp', 'mv', 'readlink', 'rm', 'stty', 'tail', 'chmod',
                 'grep', 'find', 'sort'):
        (minimal / name).symlink_to(BASH if name == 'bash' else shutil.which(name))
    env = dict(os.environ, HOME=str(home), PATH=str(minimal),
               ZDOTDIR=str(home / 'custom zsh'),
               XDG_CONFIG_HOME=str(home / 'custom config'))
    for key in ('TMUX', 'TMUX_PANE', 'BASH_ENV', 'ENV'):
        env.pop(key, None)
    (home / '.bashrc').write_text('alias mine="echo preserved"\n')
    foreign = home / '.codex/skills/tmux-reference'
    def run(*args, ok=True):
        result = sp.run([BASH, str(ROOT / 'install.sh'), *args],
                        env=env, text=True, capture_output=True)
        if ok:
            assert result.returncode == 0, result.stdout + result.stderr
        return result
    args = ('--components', 'helpers,references,skill', '--mode', 'vanilla')
    original = (home / '.bashrc').read_bytes()
    run(*args, '--dry-run')
    assert (home / '.bashrc').read_bytes() == original
    assert not (home / '.local').exists(), 'dry run wrote installation state'
    run(*args, '--yes')
    installed = (home / '.bashrc').read_bytes()
    assert b'alias mine=' in installed
    run(*args, '--yes')
    assert (home / '.bashrc').read_bytes() == installed, 'rerun changed config'
    runtime = home / '.local/share/shell-kit-runtime/bin'
    assert (runtime / 'cheat').exists() and not (runtime / 'tmenu').exists()
    assert not (home / '.tmux.conf').exists(), 'unselected component installed'
    assert (Path(env['ZDOTDIR']) / '.zshrc').exists()
    assert not (home / '.zshrc').exists(), 'ignored ZDOTDIR'
    shell = sp.run([BASH, '--noprofile', '--norc', '-ic',
                    '. "$HOME/.bash_profile"; type sfind; cheat list'],
                   env=env, text=True, capture_output=True)
    assert shell.returncode == 0 and 'sfind' in shell.stdout, shell.stderr
    assert 'Sheets:' in shell.stdout
    sample = home / 'sample'
    sample.write_text('before\nneedle.*\nafter\n\nother\n')
    pfind = sp.check_output([str(runtime / 'shell-kit-search'), 'pfind',
                            'needle.*', str(sample)], env=env, text=True)
    assert pfind == '2: needle.*\n3: after\n\n', pfind
    definitions = "alias ll='ls -l'\nalias gs='git status'\nremote ()\n{\n    ssh \"$@\"\n}\n"
    for query, expected, absent in [('l', 'll', 'remote'), ('ssh', 'remote', 'll'), ('git', 'gs', 'remote')]:
        result = sp.run([str(runtime / 'shell-kit-search'), 'aliases', query],
                        input=definitions, env=env, text=True, capture_output=True, check=True)
        assert expected in result.stdout and absent not in result.stdout, result.stdout
    # A broken legacy cached tool link must not crash a new installation.
    (runtime / 'tmux').symlink_to(home / 'removed version/tmux')
    run(*args, '--yes')
    run('--components', 'references', '--yes')
    assert not (runtime / 'shell-kit-search').exists(), 'deselection left helper'
    run('--uninstall', '--yes')
    assert (home / '.bashrc').read_bytes() == original
    assert not (runtime / 'cheat').exists()
    foreign.mkdir()
    (foreign / 'mine').write_text('unrelated skill')
    run('--components', 'helpers', '--yes')
    assert (foreign / 'mine').read_text() == 'unrelated skill'
    run('--uninstall', '--yes')
    assert (foreign / 'mine').exists(), 'uninstall removed an unowned component'
    print('PASS: dependency-free install, dry-run, selection, startup, rerun, removal')

with tempfile.TemporaryDirectory(prefix='shell-kit-conflict-') as folder:
    home = Path(folder)
    env = dict(os.environ, HOME=folder, ZDOTDIR=folder,
               XDG_CONFIG_HOME=str(home / '.config'))
    (home / '.bashrc').write_text('untouched\n')
    (home / '.zshrc').write_text('# BEGIN SHELL-KIT\nunterminated\n')
    result = sp.run([BASH, str(ROOT / 'install.sh'), '--components',
                     'helpers', '--yes'], env=env, text=True, capture_output=True)
    assert result.returncode != 0, 'malformed block accepted'
    assert (home / '.bashrc').read_text() == 'untouched\n', 'partial install'
    assert not (home / '.local/share/shell-kit').exists(), 'partial link install'
    print('PASS: malformed existing config is rejected before writes')

if os.geteuid() != 0:
    with tempfile.TemporaryDirectory(prefix='shell-kit-readonly-') as folder:
        home = Path(folder)
        env = dict(os.environ, HOME=folder, ZDOTDIR=folder)
        (home / '.bashrc').write_text('untouched\n')
        (home / '.zshrc').write_text('readonly\n')
        (home / '.zshrc').chmod(0o444)
        result = sp.run([BASH, str(ROOT / 'install.sh'), '--components',
                         'helpers', '--yes'], env=env, text=True, capture_output=True)
        assert result.returncode != 0
        assert (home / '.bashrc').read_text() == 'untouched\n', 'partial readonly install'
        assert not list(home.glob('*.shell-kit.*')), 'temporary config leaked'
        print('PASS: read-only configurations fail before any user config changes')

with tempfile.TemporaryDirectory(prefix='shell-kit-existing-') as folder:
    home = Path(folder)
    config = home / 'xdg config'
    zsh = home / 'zsh config'
    env = dict(os.environ, HOME=folder, XDG_CONFIG_HOME=str(config), ZDOTDIR=str(zsh))
    target = home / 'my actual bashrc'
    target.write_text('alias mine="echo kept"\n')
    target.chmod(0o600)
    (home / '.bashrc').symlink_to(target.name)
    (config / 'nvim').mkdir(parents=True)
    (config / 'nvim/init.lua').write_text('vim.g.original_config = 1\n')
    (home / '.vim').mkdir()
    (home / '.vim/vimrc').write_text('set number\n')
    command = [BASH, str(ROOT / 'install.sh'), '--components',
               'helpers,references,vim', '--mode', 'vanilla', '--yes']
    sp.run(command, env=env, check=True, capture_output=True)
    assert (home / '.bashrc').is_symlink(), 'installer replaced a user symlink'
    assert target.stat().st_mode & 0o777 == 0o600
    assert not (home / '.vimrc').exists(), 'installer shadowed existing Vim config'
    if shutil.which('nvim'):
        nvim = sp.run(['nvim', '--headless', '+lua print(vim.g.original_config, vim.g.loaded_shell_kit)', '+qa'],
                      env=env, text=True, capture_output=True)
        assert nvim.returncode == 0 and '1 1' in nvim.stderr, nvim.stderr
    if shutil.which('zsh'):
        result = sp.run(['zsh', '-ic', 'type sfind'], env=env, text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
    sp.run([BASH, str(ROOT / 'install.sh'), '--uninstall', '--yes'],
           env=env, check=True, capture_output=True)
    assert target.read_text() == 'alias mine="echo kept"\n'
    assert (config / 'nvim/init.lua').read_text() == 'vim.g.original_config = 1\n'
    print('PASS: custom config locations, existing Vim config, symlinks and permissions')

with tempfile.TemporaryDirectory(prefix='shell-kit-shared-rc-') as folder:
    home = Path(folder)
    env = dict(os.environ, HOME=folder, ZDOTDIR=folder)
    target = home / 'sharedrc'
    target.write_text('alias mine="echo kept"\n')
    for name in ('.bashrc', '.zshrc', '.bash_profile'):
        (home / name).symlink_to(target.name)
    sp.run([BASH, str(ROOT / 'install.sh'), '--components', 'helpers',
            '--mode', 'vanilla', '--yes'], env=env, check=True, capture_output=True)
    for name in ('bash', 'zsh'):
        if shutil.which(name):
            result = sp.run([name, '-ic', 'type sfind'], env=env, text=True, capture_output=True)
            assert result.returncode == 0, result.stderr
    assert target.read_text().count('BEGIN SHELL-KIT') == 1
    print('PASS: Bash and Zsh can share the same physical startup file')

if shutil.which('nvim'):
    with tempfile.TemporaryDirectory(prefix='shell-kit-legacy-vim-') as folder:
        home = Path(folder)
        env = dict(os.environ, HOME=folder, ZDOTDIR=folder,
                   XDG_CONFIG_HOME=str(home / '.config'))
        (home / '.vimrc').write_text('augroup CheatsheetAuto\n'
            'autocmd VimEnter * let g:legacy_opened = 1\naugroup END\n'
            '" BEGIN SHELL-KIT\naugroup CheatsheetAuto\nautocmd!\naugroup END\n'
            '" END SHELL-KIT\n')
        sp.run([BASH, str(ROOT / 'install.sh'), '--components',
                'references,vim', '--mode', 'vanilla', '--yes'],
               env=env, check=True, capture_output=True)
        result = sp.run(['nvim', '--headless', '-u', str(home / '.vimrc'),
                         '+doautocmd VimEnter', '+lua print(vim.g.legacy_opened or 0)', '+qa'],
                        env=env, text=True, capture_output=True)
        assert result.returncode == 0 and result.stderr.strip() == '0', result.stderr
        print('PASS: migrating Vim keeps the predecessor automatic sidebar disabled')

with tempfile.TemporaryDirectory(prefix='shell-kit-old-install-') as folder:
    home = Path(folder)
    env = dict(os.environ, HOME=folder, ZDOTDIR=folder)
    for key in ('TMUX', 'TMUX_PANE', 'BASH_ENV', 'ENV', 'SHELL_KIT_COMPONENTS'):
        env.pop(key, None)
    (home / '.local/share').mkdir(parents=True)
    (home / '.local/share/shell-kit').symlink_to(ROOT)
    (home / '.bashrc').write_text('. "$HOME/.local/share/shell-kit/integrations/shell.sh"\n')
    result = sp.run([BASH, '-ic', 'cheat list; type sfind; type tmenu'],
                    env=env, text=True, capture_output=True)
    assert result.returncode == 0 and 'Sheets:' in result.stdout, result.stderr
    assert not (home / '.local/state/shell-kit/install.tsv').exists()
    print('PASS: previous installation remains usable before running the new manager')
