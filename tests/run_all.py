#!/usr/bin/env python3
"""Run every check this machine can support; skip the rest with a reason.

Replaces the per-suite command list in README "Verify". A missing optional
dependency is a skip, never a failure, so the same command is correct on a
machine without tmux, fzf or the private Rich environment. The exit status is
non-zero only when a suite that could run actually failed.

    python3 -B tests/run_all.py            # everything available
    python3 -B tests/run_all.py configs    # only suites matching a name
    SHELL_KIT_TEST_BASH=/bin/bash python3 -B tests/run_all.py
    SHELL_KIT_TEST_TIMEOUT=120 python3 -B tests/run_all.py

Suites run in a temporary HOME with an isolated tmux socket, never against the
owner's live configuration or tmux server. Nothing is installed on your behalf.
"""
import os
from pathlib import Path
import shutil
import subprocess as sp
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BASH = os.environ.get('SHELL_KIT_TEST_BASH', '/bin/bash')
VENV = ROOT / '.venv/bin/python'
# The PTY suites wait on terminal output, so a broken environment wedges them
# rather than failing. Cap each one so a single hang cannot hold the whole run.
TIMEOUT = int(os.environ.get('SHELL_KIT_TEST_TIMEOUT', '900'))


def absent(*names):
    """Report the standard commands a suite needs but this machine lacks."""
    gone = [name for name in names if not shutil.which(name)]
    return 'needs ' + ', '.join(gone) if gone else ''


def absent_tmux():
    if not shutil.which('tmux'):
        return 'needs tmux'
    try:
        version = sp.run(['tmux', '-V'], text=True, capture_output=True,
                         check=True).stdout.split()[1]
    except (sp.CalledProcessError, OSError, IndexError):
        return ''  # Unreadable version: let the suite itself decide.
    digits = version.split('.')
    try:
        major = int(digits[0])
        minor = int(''.join(c for c in digits[1] if c.isdigit()) or 0)
    except (ValueError, IndexError):
        return ''
    return '' if (major, minor) >= (3, 2) else 'needs tmux >= 3.2, found ' + version


def absent_editor():
    return '' if shutil.which('vim') or shutil.which('nvim') else 'needs vim or nvim'


def absent_rich():
    if not VENV.exists():
        return 'needs the private Rich venv (enhanced install, see README)'
    if sp.run([str(VENV), '-c', 'import rich'], capture_output=True).returncode:
        return 'private venv has no Rich'
    return ''


def needs_enhanced():
    # Enhanced installs pull in the Rich pager and the fzf session picker.
    return (absent_rich() or absent_tmux() or absent_editor()
            or absent('less', 'fzf'))


def needs_vanilla_integration():
    # Vanilla drives real tmux, a pager and an editor, but never Python.
    return absent_tmux() or absent_editor() or absent('less')


# The installer's own required tools, plus what its checks drive it through.
def needs_installer():
    return absent('awk', 'cat', 'cmp', 'cp', 'date', 'dirname', 'grep', 'ln',
                  'mkdir', 'mktemp', 'mv', 'readlink', 'rm', 'tail', 'stty',
                  'chmod', 'find', 'sort', 'tr')


SUITES = [
    ('install_check', [sys.executable, '-B', 'tests/install_check.py'], needs_installer),
    ('install_keys', [sys.executable, '-B', 'tests/install_keys.py'], needs_installer),
    ('configs_check', [sys.executable, '-B', 'tests/configs_check.py'],
     lambda: absent('awk', 'tr')),
    ('legacy', [sys.executable, '-m', 'unittest', 'discover', '-s',
                'legacy/homelab-shell/scripts', '-p', 'test_*.py'], lambda: ''),
    ('tsessions_check', [sys.executable, '-B', 'tests/tsessions_check.py'],
     absent_tmux),
    ('render_check', [sys.executable, '-B', 'tests/render_check.py'], absent_rich),
    ('check', [sys.executable, '-B', 'tests/check.py'], needs_enhanced),
    ('pty_check:vanilla', [sys.executable, '-B', 'tests/pty_check.py', 'vanilla'],
     needs_vanilla_integration),
    ('pty_check:enhanced', [sys.executable, '-B', 'tests/pty_check.py'], needs_enhanced),
    ('shell_keys:vanilla', [sys.executable, '-B', 'tests/shell_keys.py', 'vanilla'],
     needs_vanilla_integration),
    ('shell_keys:enhanced', [sys.executable, '-B', 'tests/shell_keys.py'], needs_enhanced),
]


def main(patterns):
    chosen = [suite for suite in SUITES
              if not patterns or any(pattern in suite[0] for pattern in patterns)]
    if not chosen:
        print('No suite matches: ' + ' '.join(patterns), file=sys.stderr)
        print('Available: ' + ', '.join(name for name, _, _ in SUITES), file=sys.stderr)
        return 2
    print('bash %s' % BASH)
    results = []
    for name, command, unmet in chosen:
        reason = unmet()
        if reason:
            results.append((name, 'skip', 0.0, reason))
            print('SKIP %-20s %s' % (name, reason))
            continue
        print('RUN  %s' % name, flush=True)
        started = time.time()
        try:
            done = sp.run(command, cwd=ROOT, text=True, capture_output=True,
                          timeout=TIMEOUT)
        except sp.TimeoutExpired:
            elapsed = time.time() - started
            results.append((name, 'FAIL', elapsed, 'timed out after %ds' % TIMEOUT))
            print('FAIL %-20s timed out after %ds' % (name, TIMEOUT), file=sys.stderr)
            continue
        elapsed = time.time() - started
        if done.returncode:
            results.append((name, 'FAIL', elapsed, 'exit %d' % done.returncode))
            # Show the whole failure: these suites report the assertion that broke.
            sys.stdout.write(done.stdout)
            sys.stderr.write(done.stderr)
        else:
            results.append((name, 'pass', elapsed, ''))
    print('\n%-20s %-6s %8s  %s' % ('suite', 'result', 'seconds', 'note'))
    print('-' * 64)
    for name, status, elapsed, note in results:
        print('%-20s %-6s %8.1f  %s' % (name, status, elapsed, note))
    failed = [name for name, status, _, _ in results if status == 'FAIL']
    skipped = [name for name, status, _, _ in results if status == 'skip']
    print('\n%d passed, %d failed, %d skipped'
          % (len(results) - len(failed) - len(skipped), len(failed), len(skipped)))
    if failed:
        print('Failed: ' + ', '.join(failed), file=sys.stderr)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
