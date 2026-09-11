#!/usr/bin/env python3
"""Real terminal startup/closure checks, isolated from live tmux and HOME."""
import fcntl
import os
from pathlib import Path
import pty
import select
import shlex
import shutil
import signal
import struct
import subprocess as sp
import sys
import tempfile
import termios
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='shell-kit-pty-') as folder:
        home = Path(folder)
        env = dict(os.environ, HOME=folder, TERM='xterm-256color',
                   CHEAT_CLIENT='desktop', SHELL='/bin/bash',
                   XDG_CONFIG_HOME=str(home / '.config'),
                   XDG_STATE_HOME=str(home / '.local/state'),
                   PYTHONDONTWRITEBYTECODE='1')
        for name in ('TMUX', 'TMUX_PANE', 'BASH_ENV', 'ENV', 'ZDOTDIR',
                     'SSH_CONNECTION', 'SSH_CLIENT', 'SSH_TTY'):
            env.pop(name, None)
        sp.run([sys.executable, str(ROOT / 'install.py')], env=env,
               check=True, stdout=sp.DEVNULL)
        sock = str(home / 'tmux.sock')
        clients = []

        def tm(*args, check=True):
            return sp.run(['tmux', '-S', sock, *args], env=env, text=True,
                          capture_output=True, check=check).stdout.strip()

        def drain():
            for _, fd in clients:
                while select.select([fd], [], [], 0)[0]:
                    try:
                        if not os.read(fd, 65536):
                            break
                    except OSError:
                        break

        def until(predicate, label):
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                drain()
                if predicate():
                    return
                time.sleep(.05)
            screens = '\n'.join(row[0] + ':\n' + tm(
                'capture-pane', '-p', '-t', row[0], check=False)
                for row in rows() if not row[1])
            raise AssertionError(label + '\nPanes: ' + tm(
                'list-panes', '-a', '-F',
                '#{pane_id}|#{@shell_kit}|#{pane_current_command}|#{pane_active}',
                check=False) + '\nWork terminal output:\n' + screens)

        def client(profile, create=False):
            command = [str(ROOT / 'bin/cheat'), 'register']
            session = ['new-session', '-s', 'pty', '/bin/bash --noprofile --norc'] if create else ['attach-session', '-t', 'pty']
            launch = shlex.join(command) + '; exec ' + shlex.join(
                ['tmux', '-S', sock, '-f', str(home / '.tmux.conf'), *session])
            pid, fd = pty.fork()
            if pid == 0:
                fcntl.ioctl(0, termios.TIOCSWINSZ,
                            struct.pack('HHHH', 50, 180, 0, 0))
                os.execve('/bin/bash', ['bash', '--noprofile', '--norc',
                                       '-c', launch], dict(env, CHEAT_CLIENT=profile))
            clients.append((pid, fd))
            return fd

        def rows():
            raw = tm('list-panes', '-a', '-F',
                     '#{pane_id}|#{@shell_kit}|#{pane_active}|#{pane_left}|#{@shell_kit_owner}', check=False)
            return [line.split('|') for line in raw.splitlines()]

        def topics():
            return sorted(row[1] for row in rows() if row[1])

        try:
            fd = client('desktop', create=True)
            until(lambda: topics() == ['tmux'], 'desktop attach did not auto-open tmux help')
            work = next(row[0] for row in rows() if not row[1])
            assert next(row[0] for row in rows() if row[2] == '1') == work, 'startup stole focus'
            os.write(fd, b'\x1bOQ')  # Actual xterm F2, no tmux send-keys shortcut.
            until(lambda: topics() == ['tmux', 'vim'], 'F2 did not open Vim help')
            assert next(row[0] for row in rows() if row[2] == '1') == work, 'F2 stole focus'
            os.write(fd, b'\x1bOQ')
            until(lambda: topics() == ['tmux'], 'F2 did not close Vim help')
            print('PASS: real desktop attach, preserved focus, transmitted F2 toggle')
            editors = [path for name in ('vim', 'nvim') if (path := shutil.which(name))]
            assert editors, 'Vim or Neovim required'
            for editor in editors:
                os.write(fd, (shlex.join([editor, '-n', '-i', 'NONE', str(home / 'work.txt')]) + '\n').encode())
                until(lambda: topics() == ['tmux', 'vim'], Path(editor).name + ' startup did not open help')
                assert all(row[3] == '0' for row in rows() if row[1]), 'help is not stacked on left'
                assert next(row[0] for row in rows() if row[2] == '1') == work, 'editor help stole focus'
                assert next(row[4] for row in rows() if row[1] == 'vim').startswith('vim-'), 'editor owner missing'
                os.write(fd, b'\x1b:q\r')
                until(lambda: topics() == ['tmux'], Path(editor).name + ' quit left its help open')
                until(lambda: tm('display-message', '-p', '-t', work,
                                 '#{pane_current_command}', check=False) == 'bash', 'editor did not return to shell')
                print('PASS: ' + Path(editor).name + ' startup, stacking, focus and :q ownership cleanup')
            tm('new-session', '-d', '-s', 'second', '/bin/bash --noprofile --norc')
            tm('switch-client', '-t', 'second')
            until(lambda: 'tmux' in tm('list-panes', '-t', 'second', '-F', '#{@shell_kit}'), 'switching session did not apply automatic help')
            tm('switch-client', '-t', 'pty')
            tm('kill-session', '-t', 'second')
            print('PASS: session switching applies the current client profile')
            tm('detach-client', '-s', 'pty')
            phone = client('phone')
            until(lambda: tm('show-options', '-qv', '-t', 'pty',
                             '@shell_kit_client', check=False) == 'phone', 'phone attach profile was not applied')
            until(lambda: topics() == [], 'phone attach retained automatic help')
            os.write(phone, b'\x1bOP')
            until(lambda: topics() == ['tmux'], 'phone manual F1 help did not open')
            os.write(phone, b'exit\n')
            until(lambda: not tm('list-windows', '-a', check=False), 'last work shell exit left a helper-only window')
            print('PASS: phone attach suppresses auto help; last shell exit cleans helper-only window')
        finally:
            tm('kill-server', check=False)
            for pid, fd in clients:
                os.close(fd)
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                os.waitpid(pid, 0)


if __name__ == '__main__':
    main()
