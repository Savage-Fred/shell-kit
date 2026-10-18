#!/usr/bin/env python3
"""Session search/resolve checks against an isolated tmux server."""
import os
from pathlib import Path
import shutil
import subprocess as sp
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = str(ROOT / 'vanilla/tsessions')
# Honour the runner's shell so a Bash 3.2 regression cannot hide behind a pass.
BASH = os.environ.get('SHELL_KIT_TEST_BASH', '/bin/bash')


def main():
    with tempfile.TemporaryDirectory(prefix='shell-kit-sessions-') as folder:
        home = Path(folder)
        (home / 'widgets').mkdir()
        env = dict(os.environ, HOME=folder, TMUX_TMPDIR=folder,
                   PYTHONDONTWRITEBYTECODE='1')
        env.pop('TMUX', None)
        env.pop('TMUX_PANE', None)
        # Never touch the owner's real scope unit.
        scope = 'shell-kit-test-%d' % os.getpid()
        env['SHELL_KIT_TMUX_SCOPE'] = scope

        def run(*args):
            return sp.run([BASH, SCRIPT, *args], env=env, text=True,
                          capture_output=True)

        def tm(*args, check=True):
            return sp.run(['tmux', *args], env=env, text=True,
                          capture_output=True, check=check)

        empty = run('list')
        assert empty.returncode == 1, 'empty server must fail'
        assert 'No sessions yet' in empty.stderr, empty.stderr

        try:
            tm('new-session', '-d', '-s', 'alpha', '-c', folder)
            tm('new-session', '-d', '-s', 'alpha-two', '-c', folder)
            tm('new-session', '-d', '-s', 'beta', '-c', str(home / 'widgets'))
            time.sleep(0.3)  # let the panes settle so formats report a command

            listed = run('list')
            assert listed.returncode == 0, listed.stderr
            for name in ('alpha', 'alpha-two', 'beta'):
                assert name in listed.stdout, listed.stdout

            filtered = run('list', 'alpha')
            assert 'beta' not in filtered.stdout, filtered.stdout

            # Exact name beats a prefix that also matches a longer name.
            exact = run('which', 'alpha')
            assert exact.returncode == 0, exact.stderr
            assert exact.stdout.strip() == 'alpha', exact.stdout

            # Delimiter handling under LC_ALL=C must not sanitize tabs to underscores.
            c_env = dict(env, LC_ALL='C')
            c_run = lambda *args: sp.run([BASH, SCRIPT, *args], env=c_env, text=True,
                                         capture_output=True)
            c_exact = c_run('which', 'alpha')
            assert c_exact.returncode == 0, c_exact.stderr
            assert c_exact.stdout.strip() == 'alpha', c_exact.stdout
            c_listed = c_run('list')
            assert c_listed.returncode == 0, c_listed.stderr
            assert 'alpha' in c_listed.stdout and 'alpha-two' in c_listed.stdout

            # Guard HOME under set -u in render() when HOME is unset.
            no_home_env = dict(env)
            no_home_env.pop('HOME', None)
            no_home = sp.run([BASH, SCRIPT, 'list'], env=no_home_env, text=True,
                             capture_output=True)
            assert no_home.returncode == 0, no_home.stderr

            # A prefix matching two names must refuse instead of guessing.
            ambiguous = run('which', 'al')
            assert ambiguous.returncode == 1, ambiguous.stdout
            assert 'Several sessions match' in ambiguous.stderr, ambiguous.stderr

            # Working directory is searchable across windows and ignores mobile
            # help panes (@shell_kit) when choosing the displayed work context.
            by_path = run('which', 'widgets')
            assert by_path.returncode == 0, by_path.stderr
            assert by_path.stdout.strip() == 'beta', by_path.stdout
            help_pane = tm('new-window', '-P', '-F', '#{pane_id}', '-t', 'beta:',
                           '-n', 'help:tmux', '-c', folder).stdout.strip()
            tm('set-option', '-p', '-t', help_pane, '@shell_kit', 'tmux')
            time.sleep(0.2)
            assert run('which', 'widgets').stdout.strip() == 'beta'
            assert 'widgets' in run('list', 'beta').stdout
            tm('kill-pane', '-t', help_pane)

            # A pattern is data: awk -v would eat its backslash escapes.
            escaped = run('list', 'a\\lpha')
            assert 'warning' not in escaped.stderr, escaped.stderr
            assert escaped.returncode == 1, escaped.stdout

            # --help has to survive the subcommand tl/ta inject ahead of it.
            helped = run('list', '--help')
            assert helped.returncode == 0, helped.stderr
            assert 'usage:' in helped.stdout, helped.stdout

            # Only tmux can say which session is last; without a client, say so.
            # TMUX names the socket, so it must point at this isolated server.
            socket = tm('display-message', '-p', '#{socket_path}').stdout.strip()
            env['TMUX'] = '%s,0,0' % socket
            stranded = run('attach')
            env.pop('TMUX')
            assert stranded.returncode == 1, stranded.stdout
            assert 'No previous session' in stranded.stderr, stranded.stderr

            missing = run('which', 'nosuchsession')
            assert missing.returncode == 1, missing.stdout
            assert 'No session matches' in missing.stderr, missing.stderr
            # The failure still shows what is available.
            assert 'alpha' in missing.stderr, missing.stderr
            # HOME abbreviation must respect a path boundary: a sibling
            # directory sharing the HOME prefix is not inside HOME.
            sibling = Path(str(home) + 'ow')
            sibling.mkdir()
            try:
                tm('new-session', '-d', '-s', 'outside', '-c', str(sibling))
                time.sleep(0.3)  # the pane reports its directory once the shell starts
                shown = run('list', 'outside')
                assert '~ow' not in shown.stdout, shown.stdout
                assert str(sibling) in shown.stdout, shown.stdout
            finally:
                sibling.rmdir()
            # Creating the server through the scoped runner must leave it in
            # its own cgroup, so the terminal dying cannot take it along.
            if shutil.which('systemd-run'):
                tm('kill-server', check=False)
                time.sleep(0.3)
                made = run('run', 'new-session', '-d', '-s', 'scoped')
                assert made.returncode == 0, made.stderr
                time.sleep(0.5)
                pid = tm('list-sessions', '-F', '#{pid}').stdout.strip().splitlines()[0]
                if sys.platform == 'linux':
                    cgroup = Path('/proc/%s/cgroup' % pid).read_text()
                    assert scope in cgroup, cgroup
                # Starting another server when the base scope unit is already
                # active must not stop the live server in that scope.
                other_tmp = home / 'other-sock'
                other_tmp.mkdir()
                other_env = dict(env, TMUX_TMPDIR=str(other_tmp))
                try:
                    second = sp.run([BASH, SCRIPT, 'run', 'new-session', '-d', '-s', 'second-srv'],
                                    env=other_env, text=True, capture_output=True)
                    assert second.returncode == 0, second.stderr
                    assert 'scoped' in tm('list-sessions', '-F', '#{session_name}').stdout
                finally:
                    sp.run(['tmux', 'kill-server'], env=other_env, capture_output=True)
                # Restarting with the same scope unit must cleanly clear any lingering unit.
                tm('kill-server', check=False)
                time.sleep(0.3)
                restarted = run('run', 'new-session', '-d', '-s', 'scoped-restarted')
                assert restarted.returncode == 0, restarted.stderr
                # Opting out must fall back to a plain, unscoped tmux.
                tm('kill-server', check=False)
                time.sleep(0.3)
                env['SHELL_KIT_TMUX_SCOPE'] = 'off'
                plain = run('run', 'new-session', '-d', '-s', 'unscoped')
                assert plain.returncode == 0, plain.stderr
                time.sleep(0.4)
                pid = tm('list-sessions', '-F', '#{pid}').stdout.strip().splitlines()[0]
                if sys.platform == 'linux':
                    assert scope not in Path('/proc/%s/cgroup' % pid).read_text()
                env['SHELL_KIT_TMUX_SCOPE'] = scope

            # Suspending must reach the work, not the idle pane shell: job
            # control gives each job its own process group.
            tm('kill-server', check=False)
            time.sleep(0.3)
            tm('new-session', '-d', '-s', 'busy')
            time.sleep(0.4)
            tm('send-keys', '-t', 'busy', 'sleep 600', 'Enter')
            time.sleep(1.0)
            pane = tm('list-panes', '-s', '-t', 'busy', '-F', '#{pane_pid}').stdout.strip()
            kid = sp.run(['ps', '-eo', 'pid,ppid'], text=True, capture_output=True).stdout
            child = [l.split()[0] for l in kid.splitlines()[1:]
                     if len(l.split()) > 1 and l.split()[1] == pane]
            assert child, 'no child process in the pane'
            state = lambda: sp.run(['ps', '-o', 'state=', '-p', child[0]],
                                   text=True, capture_output=True).stdout.strip()[:1]
            assert state() == 'S', state()
            frozen = run('freeze', 'busy')
            assert frozen.returncode == 0, frozen.stderr
            for _ in range(30):
                if state() == 'T':
                    break
                time.sleep(0.1)
            assert state() == 'T', 'freeze did not stop the work: ' + state()
            assert run('thaw', 'busy').returncode == 0
            for _ in range(30):
                if state() == 'S':
                    break
                time.sleep(0.1)
            assert state() == 'S', 'thaw did not resume the work: ' + state()

            # Non-empty pattern required for kill, freeze, and thaw
            for act in ('kill', 'freeze', 'thaw'):
                no_arg = run(act)
                assert no_arg.returncode == 1, f'{act} without arguments must fail'
                assert f'usage: tsessions {act} PATTERN' in no_arg.stderr, no_arg.stderr

            # Colon target kills window without killing session
            tm('new-window', '-t', 'busy', '-n', 'subwin')
            time.sleep(0.3)
            assert 'subwin' in tm('list-windows', '-t', 'busy', '-F', '#{window_name}').stdout
            kill_win = run('kill', 'busy:subwin')
            assert kill_win.returncode == 0, kill_win.stderr
            assert 'subwin' not in tm('list-windows', '-t', 'busy', '-F', '#{window_name}').stdout

            # Killing removes exactly the named session.
            tm('new-session', '-d', '-s', 'keepme')
            time.sleep(0.3)
            killed = run('kill', 'busy')
            assert killed.returncode == 0, killed.stderr
            remaining = tm('list-sessions', '-F', '#{session_name}').stdout.split()
            assert 'busy' not in remaining, remaining
            assert 'keepme' in remaining, remaining
        finally:
            tm('kill-server', check=False)
            sp.run(['systemctl', '--user', 'stop', scope + '.scope'],
                   capture_output=True)
    print('tsessions checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
