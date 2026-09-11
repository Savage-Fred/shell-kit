#!/usr/bin/env python3
"""Exercise the actual selector, cancellation, confirmation and terminal cleanup."""
import os
from pathlib import Path
import pty
import select
import signal
import struct
import fcntl
import tempfile
import termios
import time

ROOT = Path(__file__).resolve().parents[1]
BASH = os.environ.get('SHELL_KIT_TEST_BASH', '/bin/bash')

def exercise(home, keys, confirm):
    def snapshot():
        return {str(p.relative_to(home)): os.readlink(p) if p.is_symlink() else
                p.read_bytes() if p.is_file() else None for p in home.rglob('*')}
    before = snapshot()
    pid, fd = pty.fork()
    if pid == 0:
        fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
        env = dict(os.environ, HOME=str(home), ZDOTDIR=str(home),
                   XDG_CONFIG_HOME=str(home / '.config'), TERM='xterm-256color')
        os.execve(BASH, ['bash', str(ROOT / 'install.sh')], env)
    output = bytearray()
    def until(text):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if text in output:
                return
            if select.select([fd], [], [], .05)[0]:
                try:
                    output.extend(os.read(fd, 65536))
                except OSError:
                    break
        raise AssertionError(bytes(output[-1500:]))
    exited = False
    try:
        until(b'Arrows move')
        os.write(fd, keys)
        if confirm is not None:
            until(b'Apply this plan?')
            assert snapshot() == before, 'Enter applied before confirmation'
            os.write(fd, confirm)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if select.select([fd], [], [], .05)[0]:
                try:
                    output.extend(os.read(fd, 65536))
                except OSError:
                    pass
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                exited = True
                assert status in (0, 130 << 8), bytes(output[-1500:])
                break
        assert exited, 'selector did not exit for ' + repr(keys) + '\n' + repr(bytes(output[-2000:]))
        flags = termios.tcgetattr(fd)[3]
        assert flags & termios.ECHO and flags & termios.ICANON, 'terminal mode leaked'
    finally:
        if not exited:
            os.kill(pid, signal.SIGTERM)
            os.waitpid(pid, 0)
        os.close(fd)

with tempfile.TemporaryDirectory(prefix='shell-kit-selector-') as folder:
    base = Path(folder)
    for cancel in (b'q', b'\x03'):
        home = base / ('quit' if cancel == b'q' else 'interrupt')
        home.mkdir()
        exercise(home, cancel, None)
        assert not list(home.iterdir()), 'cancellation changed HOME'
    home = base / 'decline'
    home.mkdir()
    exercise(home, b' \x1b[B \r', b'n')
    assert not list(home.iterdir()), 'declined confirmation changed HOME'
    home = base / 'save'
    home.mkdir()
    # Move down to references, back up, then select helpers and references.
    exercise(home, b'\x1b[B\x1b[A \x1b[B \r', b'y')
    runtime = home / '.local/share/shell-kit-runtime/bin'
    assert (runtime / 'cheat').exists() and (runtime / 'shell-kit-search').exists()
    assert not (runtime / 'tmenu').exists()
    # Reload the saved selections, deselect helpers, leave references enabled.
    exercise(home, b' \r', b'y')
    assert not (runtime / 'shell-kit-search').exists() and (runtime / 'cheat').exists()
    print('PASS: arrows, Space, Enter, y/n, saved selection, quit and Ctrl-C cleanup')
