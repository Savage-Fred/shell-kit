#!/usr/bin/env python3
"""Drive the enhanced session manager through a PTY on an isolated tmux socket."""
import fcntl
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess as sp
import sys
import tempfile
import termios
import time

ROOT = Path(__file__).resolve().parents[1]
TMENU = str(ROOT / 'bin/tmenu')


class Picker:
    """One tmenu process on a pseudo-terminal that answers fzf's cursor queries."""

    def __init__(self, env):
        self.seen = b''
        self.cursor = 0
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 120, 0, 0))
            os.execvpe(TMENU, [TMENU], env)

    def pump(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            ready, _, _ = select.select([self.fd], [], [], 0.05)
            if not ready:
                continue
            try:
                chunk = os.read(self.fd, 65536)
            except OSError:
                return
            self.seen += chunk
            for _ in range(chunk.count(b'\x1b[6n')):
                os.write(self.fd, b'\x1b[1;1R')

    def expect(self, text, seconds=10):
        """Wait for text not yet consumed by an earlier expect."""
        end = time.time() + seconds
        while time.time() < end:
            found = self.seen.find(text.encode(), self.cursor)
            if found >= 0:
                self.cursor = found + len(text)
                return
            self.pump(0.1)
        raise AssertionError('never saw %r; tail: %r' % (text, self.seen[-400:]))

    def keys(self, data):
        for byte in data:
            os.write(self.fd, bytes([byte]))
            self.pump(0.15)

    def finish(self, seconds=5):
        end = time.time() + seconds
        while time.time() < end:
            done, status = os.waitpid(self.pid, os.WNOHANG)
            if done:
                self.pid = 0
                return os.waitstatus_to_exitcode(status)
            self.pump(0.1)
        raise AssertionError('tmenu did not exit; tail: %r' % self.seen[-400:])

    def stop(self):
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGKILL)
                os.waitpid(self.pid, 0)
            except (ProcessLookupError, ChildProcessError):
                pass
        try:
            os.close(self.fd)
        except OSError:
            pass


with tempfile.TemporaryDirectory(prefix='shell-kit-tmenu-') as folder:
    env = dict(os.environ, HOME=folder, TMUX_TMPDIR=folder, TERM='xterm-256color',
               SHELL_KIT_TMUX_SCOPE='off', SHELL='/bin/sh')
    for key in ('TMUX', 'TMUX_PANE', 'FZF_DEFAULT_OPTS', 'FZF_DEFAULT_OPTS_FILE'):
        env.pop(key, None)

    def tm(*args):
        return sp.run(['tmux', '-f', '/dev/null', *args], env=env, text=True,
                      capture_output=True, timeout=10)

    def sessions():
        return sorted(tm('list-sessions', '-F', '#{session_name}').stdout.split())

    def until(expected, seconds=10):
        end = time.time() + seconds
        while time.time() < end:
            picker.pump(0.1)
            if sessions() == expected:
                return
        raise AssertionError('sessions are %r, wanted %r; tail: %r'
                             % (sessions(), expected, picker.seen[-400:]))

    picker = None
    try:
        for name in ('alpha', 'beta'):
            assert tm('new-session', '-d', '-s', name, 'sleep 600').returncode == 0
        picker = Picker(env)
        picker.expect('alpha')
        version = sp.check_output(['fzf', '--version'], text=True).split()[0]
        if tuple(map(int, version.split('.')[:2])) < (0, 19):
            assert b'Create: tn NAME' in picker.seen and b'Ctrl-X: kill' not in picker.seen
            picker.keys(b'\x1b')
            assert picker.finish() == 0
            print('PASS: installed legacy fzf offers the plain picker')
            sys.exit(0)
        assert b'Ctrl-N: new' in picker.seen and b'Ctrl-X: kill' in picker.seen, picker.seen[-400:]

        picker.keys(b'\x0e')                       # Ctrl-N, blank answer: nothing is created
        picker.expect('New session name')
        picker.keys(b'\r')
        picker.pump(1)
        assert sessions() == ['alpha', 'beta'], sessions()
        picker.keys(b'\x0e')
        picker.expect('New session name')
        picker.keys(b'gamma\r')
        until(['alpha', 'beta', 'gamma'])
        print('PASS: Ctrl-N creates a named session and a blank name cancels')

        picker.keys(b'beta')                       # filter, then Ctrl-R renames the match
        picker.pump(0.5)
        picker.keys(b'\x12')
        picker.expect('Rename beta to')
        picker.keys(b'delta\r')
        until(['alpha', 'delta', 'gamma'])
        print('PASS: Ctrl-R renames the highlighted session')

        picker.keys(b'gamma')                      # the filter was cleared by the rename
        picker.pump(0.5)
        picker.keys(b'\x18')
        picker.expect('Kill session gamma')
        picker.keys(b'n\r')
        picker.pump(1)
        assert sessions() == ['alpha', 'delta', 'gamma'], 'a declined kill removed a session'
        picker.keys(b'gamma')
        picker.pump(0.5)
        picker.keys(b'\x18')
        picker.expect('Kill session gamma')
        picker.keys(b'y\r')
        until(['alpha', 'delta'])
        print('PASS: Ctrl-X kills only after confirmation')

        picker.keys(b'\x1b')
        assert picker.finish() == 0
        assert tm('list-clients').stdout == '', 'cancelling attached a client'
        picker.stop()

        picker = Picker(env)                       # the refreshed list still attaches
        picker.expect('alpha')
        picker.keys(b'delta')
        picker.pump(0.5)
        picker.keys(b'\r')
        end = time.time() + 10
        while time.time() < end and tm('list-clients', '-F', '#{session_name}').stdout.split() != ['delta']:
            picker.pump(0.1)
        assert tm('list-clients', '-F', '#{session_name}').stdout.split() == ['delta'], picker.seen[-400:]
        print('PASS: Enter still attaches to the chosen session and Esc cancels')
    finally:
        tm('kill-server')
        if picker:
            picker.stop()

    # An fzf without reload keeps the plain picker: no management bindings.
    fake = Path(folder) / 'bin'
    fake.mkdir()
    record = Path(folder) / 'fzf-args'
    (fake / 'fzf').write_text('#!/bin/sh\ncase $1 in --version) echo 0.18.0;; --help) echo usage;; '
                              '*) printf "%s\\n" "$@" > "' + str(record) + '"; exit 130;; esac\n')
    (fake / 'fzf').chmod(0o755)
    old = dict(env, PATH=str(fake) + os.pathsep + env['PATH'])
    try:
        assert tm('new-session', '-d', '-s', 'alpha', 'sleep 600').returncode == 0
        picker = Picker(old)
        assert picker.finish() == 0
        arguments = record.read_text()
        assert 'ctrl-x' not in arguments and 'Create: tn NAME' in arguments, arguments
        print('PASS: an fzf without reload keeps the plain picker')
    finally:
        tm('kill-server')
        picker.stop()
