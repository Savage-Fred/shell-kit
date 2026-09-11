#!/usr/bin/env python3
"""Real F-key input with pending shell/editor text; isolated temporary HOME."""
import fcntl
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import struct
import subprocess as sp
import sys
import tempfile
import termios
import time

ROOT = Path(__file__).resolve().parents[1]
MODE = sys.argv[1] if len(sys.argv) > 1 else 'enhanced'
assert MODE in ('vanilla', 'enhanced')
if MODE == 'enhanced':
    assert (ROOT / '.venv/bin/python').exists(), 'Prepare enhanced dependencies first (see README)'
    sp.run([str(ROOT / '.venv/bin/python'), '-c', 'import rich'], check=True)


def main():
    with tempfile.TemporaryDirectory(prefix='shell-kit-keys-') as tmp:
        home = Path(tmp)
        env = dict(os.environ, HOME=tmp, TERM='xterm-256color',
                   CHEAT_CLIENT='phone', PS1='KEYTEST> ',
                   XDG_CONFIG_HOME=str(home / '.config'))
        for key in ('TMUX', 'TMUX_PANE', 'BASH_ENV', 'ENV', 'ZDOTDIR',
                    'SSH_CONNECTION', 'SSH_CLIENT', 'SSH_TTY'):
            env.pop(key, None)
        sp.run(['bash', str(ROOT / 'install.sh'), '--components', 'helpers,references,tmux,vim,skill', '--mode', MODE, '--yes'], env=env,
               check=True, stdout=sp.DEVNULL)
        for rc in ('.bashrc', '.zshrc'):
            with (home / rc).open('a') as stream:
                stream.write("\nPS1='KEYTEST> '\n")
        failures = []
        for name in ('bash', 'zsh', 'vim'):
            binary = shutil.which(name)
            if not binary:
                print('SKIP: ' + name + ' unavailable')
                continue
            pid, fd = pty.fork()
            if pid == 0:
                fcntl.ioctl(0, termios.TIOCSWINSZ,
                            struct.pack('HHHH', 45, 180, 0, 0))
                args = [binary, '-i'] if name != 'vim' else [binary, '-n', '-i', 'NONE', str(home / 'edited')]
                os.execve(binary, args, env)
            output = bytearray()

            def drain():
                while select.select([fd], [], [], 0)[0]:
                    try:
                        block = os.read(fd, 65536)
                    except OSError:
                        break
                    if not block:
                        break
                    output.extend(block)

            def until(condition, reason):
                deadline = time.monotonic() + 7
                while time.monotonic() < deadline:
                    drain()
                    if condition():
                        return
                    time.sleep(.05)
                raise AssertionError(reason + '\n' + repr(bytes(output[-2000:])))

            def send(data):
                os.write(fd, data)

            try:
                if name != 'vim':
                    until(lambda: b'KEYTEST>' in output, 'shell prompt absent')
                    for topic, key in [('tmux', b'\x1bOP'), ('vim', b'\x1bOQ')]:
                        result = home / (name + '-' + topic)
                        send(('printf preserved > ' + str(result)).encode())
                        output.clear()
                        send(key)
                        until(lambda: (b'stay oriented' if topic == 'tmux' else b'move, select') in output,
                              name + ': ' + topic + ' viewer did not open')
                        send(key)
                        time.sleep(.2)
                        send(b'\r')
                        until(result.exists, name + ': F-key failed to return pending shell command')
                        assert result.read_text() == 'preserved'
                    print('PASS: ' + name + ' F1/F2 open-close preserves pending command')
                else:
                    until(lambda: b'edited' in output, 'Vim not ready')
                    send(b'ibefore')
                    send(b'\x1bOQ')
                    until(lambda: b'vim.md' in output or b'move, select' in output,
                          'Vim F2 did not open reference')
                    send(b'after\x1bOQ')
                    time.sleep(.2)
                    send(b'\x1b:wq\r')
                    until(lambda: (home / 'edited').exists(), 'Vim did not save after F2 toggle')
                    assert (home / 'edited').read_text() == 'beforeafter\n', 'Vim focus or insert text lost'
                    print('PASS: standalone Vim real F2 toggle preserves insert text and work focus')
            except AssertionError as exc:
                failures.append(name + ': ' + str(exc))
                print('FAIL: ' + failures[-1])
            finally:
                os.close(fd)
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                os.waitpid(pid, 0)
        if failures:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
