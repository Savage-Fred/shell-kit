#!/usr/bin/env python3
"""Session search/resolve checks against an isolated tmux server."""
import os
from pathlib import Path
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

            # A prefix matching two names must refuse instead of guessing.
            ambiguous = run('which', 'al')
            assert ambiguous.returncode == 1, ambiguous.stdout
            assert 'Several sessions match' in ambiguous.stderr, ambiguous.stderr

            # Working directory is searchable, not just the session name.
            by_path = run('which', 'widgets')
            assert by_path.returncode == 0, by_path.stderr
            assert by_path.stdout.strip() == 'beta', by_path.stdout

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
        finally:
            tm('kill-server', check=False)
    print('tsessions checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
