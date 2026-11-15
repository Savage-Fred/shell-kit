#!/usr/bin/env python3
"""Runnable integration checks. Uses a temporary HOME and private tmux socket."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess as sp
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
assert (ROOT / '.venv/bin/python').exists(), 'Prepare enhanced dependencies first (see README)'
sp.run([str(ROOT / '.venv/bin/python'), '-c', 'import rich'], check=True)

def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module

controller = load('controller', ROOT / 'bin/cheat-enhanced')
# A client can depart after validation but before the hook changes its pane.
with tempfile.TemporaryDirectory() as state, patch.object(controller, 'STATE', Path(state)):
    failure = sp.CalledProcessError(1, ['tmux', 'list-panes'])
    with patch.object(controller, 'tm', side_effect=['/test-tty', '', failure, '']):
        controller.main(['attach', '%1', '/test-tty'])
    # Real errors for a still-attached client must remain visible.
    with patch.object(controller, 'tm', side_effect=['/test-tty', '', failure, '/test-tty']):
        try:
            controller.main(['attach', '%1', '/test-tty'])
        except sp.CalledProcessError:
            pass
        else:
            raise AssertionError('active-client hook error was hidden')

# A forgotten topic or hook argument stays a cheat: message, never a raw traceback.
with tempfile.TemporaryDirectory(prefix='shell-kit-args-') as tmp:
    bare = dict(os.environ, HOME=tmp)
    bare.pop('TMUX', None)
    bare.pop('TMUX_PANE', None)
    in_tmux = dict(bare, TMUX=tmp + '/absent.sock,0,0', TMUX_PANE='%0')
    for missing, environment in [(['view'], bare), (['edit'], bare), (['open'], bare), (['close'], bare),
                                 (['auto'], bare), (['cleanup'], bare), (['close-owner'], in_tmux)]:
        done = sp.run([str(ROOT / 'bin/cheat'), *missing], env=environment, text=True,
                      stdout=sp.PIPE, stderr=sp.PIPE)
        assert done.returncode == 1, (missing, done.returncode, done.stderr)
        assert done.stderr.startswith('cheat: ') and 'Traceback' not in done.stderr, (missing, done.stderr)
# A recycled tty must not inherit a months-old help policy. Expiry also keeps
# the record directory from accumulating entries for ttys that are long gone.
with tempfile.TemporaryDirectory() as state, patch.object(controller, 'STATE', Path(state)):
    current, expired = Path(state) / 'client-current', Path(state) / 'client-expired'
    current.write_text('desktop')
    expired.write_text('desktop')
    past = time.time() - (controller.CLIENT_RECORD_DAYS + 1) * 86400
    os.utime(expired, (past, past))
    controller.expire_clients()
    assert current.exists(), 'expiry removed a record still inside its window'
    assert not expired.exists(), 'expiry kept a record past its window'

for sheet in (ROOT / 'sheets').glob('*.md'):
    assert all(len(line) <= 80 for line in sheet.read_text().splitlines()), sheet

# A function key is only usable when every integration agrees about it. Wiring
# one of the five and forgetting another is the failure mode when adding a sheet.
shell_source = (ROOT / 'integrations/shell.sh').read_text()
tmux_source = (ROOT / 'integrations/tmux.conf').read_text()
vim_source = (ROOT / 'integrations/vim.vim').read_text()
lesskey_source = (ROOT / 'integrations/lesskey').read_text()
compiled_keys = (ROOT / 'integrations/less.keys').read_bytes()
for key, topic, code in [
        ('F1', 'tmux', 11), ('F2', 'vim', 12), ('F3', 'grep', 13),
        ('F4', 'aliases', 14), ('F5', 'git', 15), ('F6', 'agents', 17)]:
    assert (ROOT / 'sheets' / (topic + '.md')).exists(), topic
    assert 'function _sk_%s ' % topic in shell_source, key
    assert '"\\e[%d~"' % code in shell_source, (key, 'bash binding')
    assert "'\\e[%d~' _sk_%s" % (code, topic) in shell_source, (key, 'zsh binding')
    assert 'bind-key -n %s ' % key in tmux_source, (key, 'tmux binding')
    assert "['%s','%s']" % (key, topic) in vim_source, (key, 'vim binding')
    assert '\\e[%d~ quit' % code in lesskey_source, (key, 'lesskey source')
    assert b'\x1b[%d~' % code in compiled_keys, (key, 'compiled less.keys is stale')

with tempfile.TemporaryDirectory(prefix='shell-kit-check-') as tmp:
    home = Path(tmp)
    env = dict(os.environ, HOME=tmp, TERM='xterm-256color', CHEAT_CLIENT='desktop')
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)
    def call(*cmd, input=None, check=True):
        # Never inherit the caller's stdin: tmenu's no-terminal fallback reads a choice from it.
        return sp.run(cmd, env=env, input=input, stdin=None if input is not None else sp.DEVNULL,
                      text=True, stdout=sp.PIPE, stderr=sp.PIPE, check=check)
    call('bash', str(ROOT / 'install.sh'), '--components', 'helpers,references,tmux,vim,skill', '--mode', 'enhanced', '--yes')
    before = (home / '.bashrc').read_text()
    call('bash', str(ROOT / 'install.sh'), '--components', 'helpers,references,tmux,vim,skill', '--mode', 'enhanced', '--yes')
    assert (home / '.bashrc').read_text() == before, 'installer must be idempotent'
    sample = home / 'file with spaces.txt'
    sample.write_text('before\nneedle.* literal\nafter\n\nother\nneedle.* second\nlast\n')
    found = call(str(ROOT / 'vanilla/shell-kit-search'), 'sfind', 'needle.*', tmp).stdout
    assert str(sample) in found and 'before' in found and 'after' in found
    block = call(str(ROOT / 'vanilla/shell-kit-search'), 'pfind', 'needle.*', str(sample)).stdout
    assert '1: before' not in block and '3: after' in block and '7: last' in block
    (home / 'name with spaces').mkdir()
    assert str(home / 'name with spaces') in call(str(ROOT / 'vanilla/shell-kit-search'), 'dfind', 'with', tmp).stdout
    call('bash', '-n', str(ROOT / 'integrations/shell.sh'))
    if shutil.which('zsh'):
        call('zsh', '-n', str(ROOT / 'integrations/shell.sh'))
    for shell in ('bash', 'zsh'):
        if shutil.which(shell):
            fixture = 'alias tn="echo existing"; . ' + str(ROOT / 'integrations/shell.sh') + '; aliases tn; type td'
            output = call(shell, '-fic', fixture).stdout
            assert 'echo existing' in output and 'td' in output, 'existing alias broke shell startup'
    sock = str(home / 'tmux.sock')
    def tm(*args):
        return call('tmux', '-S', sock, *args).stdout.strip()
    try:
        tm('-f', '/dev/null', 'new-session', '-d', '-s', 'check', '-x', '180', '-y', '50', 'sleep 300')
        pane = tm('display-message', '-p', '#{pane_id}')
        env.update(TMUX=f'{sock},0,0', TMUX_PANE=pane)
        def cheat(*args):
            return call(str(ROOT / 'bin/cheat'), *args).stdout
        assert cheat('tip').startswith('Sheila: ')
        def rows():
            return [r.split('|') for r in tm('list-panes', '-F', '#{pane_id}|#{@shell_kit}|#{pane_left}|#{pane_active}').splitlines()]
        env['FZF_DEFAULT_OPTS'] = '--filter=shell-kit-no-match-should-cancel'
        call(str(ROOT / 'bin/tmenu'))
        env.pop('FZF_DEFAULT_OPTS')
        assert len(rows()) == 1, 'session picker with no answer on stdin changed panes'
        tm('set-environment', '-g', 'CHEAT_THEME', 'dark')
        env['CHEAT_THEME'] = 'light'
        cheat('tmux')
        assert len(rows()) == 2, rows()
        help_id = next(r[0] for r in rows() if r[1])
        capture = ''
        for _ in range(100):
            capture = tm('capture-pane', '-e', '-p', '-t', help_id)
            if 'focus pane' in capture and 'q/F1-F6 close' in capture:
                break
            time.sleep(.02)
        assert 'q/F1-F6 close' in capture, 'pager footer lost its close instructions'
        assert '\x1b[34m' in capture, 'caller light theme lost to dark server environment'
        assert [r[0] for r in rows() if r[3] == '1'] == [pane], 'opening stole focus'
        cheat('tmux')
        assert len(rows()) == 1, 'same toggle failed to close'
        cheat('open', 'tmux')
        tm('split-window', '-d', '-v', '-t', pane, 'sleep 300')
        cheat('auto', 'vim', pane, 'editor-test')
        r = rows()
        assert len(r) == 4 and all(x[2] == '0' for x in r if x[1]), r
        cheat('auto', 'vim', pane, 'editor-test')
        assert len(rows()) == 4, 'duplicate sheet'
        cheat('close-owner', 'other-editor')
        assert len(rows()) == 4
        cheat('close-owner', 'editor-test')
        assert len(rows()) == 3
        cheat('auto', 'vim', pane, 'editor-test')
        stale = call(str(ROOT / 'bin/cheat'), 'attach', '%999999', '/gone-client', check=False)
        assert stale.returncode == 0, 'late hook for a deleted pane must exit quietly'
        previous = rows()
        cheat('attach', pane, '/unregistered-client')
        assert rows() == previous, 'detached client must not change current help policy'
        cheat('close-owner', 'editor-test')
        tm('set-option', '@shell_kit_client', 'phone')
        assert cheat('profile').strip() == 'phone'
        # Real tmux config parsing; hook can execute with a terminal client later.
        tm('source-file', str(ROOT / 'integrations/tmux.conf'))
        assert 'shell-kit' in tm('list-keys', '-T', 'root', 'F1')
        cheat('close', 'tmux')
        assert len(rows()) == 2
        tm('resize-window', '-t', pane, '-x', '90', '-y', '30')
        cheat('grep')
        assert len(tm('list-windows').splitlines()) == 2, 'narrow help needs its own resizable window'
        help_pane = tm('display-message', '-p', '#{pane_id}')
        assert help_pane != pane
        tm('resize-window', '-t', help_pane, '-x', '155', '-y', '30')
        assert tm('display-message', '-p', '-t', help_pane, '#{pane_width}') == '155'
        cheat('grep', help_pane)
        assert len(tm('list-windows').splitlines()) == 1, 'help toggle must restore work window'
        # tmux names the *current* window to the pane-exited hook, not the one the
        # pane left. A dedicated help window must survive that, and a sidebar
        # orphaned in a background window must still be closed.
        def windows():
            return tm('list-windows', '-F', '#{window_id}').splitlines()
        def helper(*flags, name=None, sheet='tmux'):
            made = tm('new-window', *flags, '-P', '-F', '#{window_id}', *(['-n', name] if name else []), 'sleep 300')
            tm('set-option', '-p', '-t', made, '@shell_kit', sheet)
            return made
        work = tm('display-message', '-p', '#{window_id}')
        # A real sidebar beside the working pane: it must stay while that pane lives.
        beside = tm('split-window', '-d', '-t', work, '-P', '-F', '#{pane_id}', 'sleep 300')
        tm('set-option', '-p', '-t', beside, '@shell_kit', 'vim')
        working_panes = tm('list-panes', '-t', work, '-F', '#{pane_id}')
        assert len(working_panes.splitlines()) >= 2
        dedicated = helper('-d', name='help:tmux')
        orphan = helper('-d', sheet='grep')
        cheat('cleanup', dedicated)
        assert dedicated in windows(), 'cleanup closed a dedicated help window'
        assert orphan not in windows(), 'cleanup left an orphaned help sidebar'
        assert tm('list-panes', '-t', work, '-F', '#{pane_id}') == working_panes, 'cleanup touched a working window'
        # The same through the real hook: the help window is current while the
        # last pane of another window exits.
        tm('select-window', '-t', dedicated)
        orphan = helper('-d', sheet='grep')
        tm('new-window', '-d', 'sleep 1')
        for _ in range(100):
            if orphan not in windows():
                break
            time.sleep(0.1)
        assert orphan not in windows(), 'pane-exited hook did not clean an orphaned sidebar'
        assert dedicated in windows(), 'an unrelated pane exit closed the help window'
        assert tm('list-panes', '-t', work, '-F', '#{pane_id}') == working_panes, 'the hook touched a working window'
        # A tag inherited from a wider scope is not a sheet: nothing may be closed.
        plain = tm('new-window', '-d', '-P', '-F', '#{window_id}', 'sleep 300')
        tm('set-option', '-g', '@shell_kit', 'stray')
        cheat('cleanup', work)
        tm('set-option', '-gu', '@shell_kit')
        assert plain in windows() and dedicated in windows(), 'an inherited tag closed windows'
        assert tm('list-panes', '-t', work, '-F', '#{pane_id}') == working_panes, 'an inherited tag closed panes'
        tm('select-window', '-t', work)
        tm('kill-window', '-t', dedicated)
        tm('kill-window', '-t', plain)
        tm('kill-pane', '-t', beside)
        assert windows() == [work]
        print('PASS: search, installer, shell syntax, tmux focus/stack/toggle/ownership/profile, hook cleanup')
    finally:
        sp.run(['tmux', '-S', sock, 'kill-server'], env=env, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)
    # Standalone editor keeps active work buffer and dismisses its help on quit.
    editor = shutil.which('nvim') or shutil.which('vim')
    script = home / 'editor-check.vim'
    result = home / 'vim-result'
    script.write_text('set columns=180 lines=50\nsource ' + str(ROOT / 'integrations/vim.vim') + '\n' +
        'call ShellKitSheet("vim", 0)\n' +
        'call assert_equal(2, winnr("$"))\ncall assert_equal("", get(w:, "shell_kit", ""))\n' +
        'call ShellKitSheet("grep", 0)\ncall assert_equal(3, winnr("$"))\n' +
        'call ShellKitSheet("vim", 0)\ncall assert_equal(2, winnr("$"))\n' +
        'call ShellKitCleanup()\ncall assert_equal(1, winnr("$"))\n' +
        'call writefile(v:errors, ' + repr(str(result)) + ')\nqa!\n')
    call(editor, '-u', 'NONE', '-i', 'NONE', '-n', '-es', '-S', str(script))
    assert result.read_text() == '', result.read_text()
    call('bash', str(ROOT / 'install.sh'), '--uninstall', '--yes')
    assert 'BEGIN SHELL-KIT' not in (home / '.bashrc').read_text()
    assert not (home / '.local/share/shell-kit').exists()
    print('PASS: standalone Vim/Neovim stacking, focus, toggle, cleanup and uninstall')
