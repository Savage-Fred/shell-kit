#!/usr/bin/env python3
"""Automated validation and portability test suite for shell-kit.

Satisfies Milestone 1 / Acceptance Criterion 7:
1. Shell syntax validation (bash -n on all core scripts).
2. Clean-HOME isolated install & uninstall cycle with set -u (nounset) subshell verification.
3. Missing optional tool fallbacks (graceful operation when optional tools like rg, fzf, bat, less are missing).
4. Idempotency verification (consecutive runs produce identical file hashes).
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess as sp
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASH = os.environ.get('SHELL_KIT_TEST_BASH', '/bin/bash')


def log(msg):
    print(f"[portability_check] {msg}", flush=True)


# ============================================================================
# Tier 1: Shell Syntax Verification (bash -n)
# ============================================================================
def check_shell_syntax():
    log("Tier 1: Verifying shell syntax with bash -n...")
    scripts_to_check = [
        ROOT / 'install.sh',
        ROOT / 'integrations' / 'shell.sh',
        ROOT / 'vanilla' / 'cheat',
        ROOT / 'vanilla' / 'configs',
        ROOT / 'vanilla' / 'shell-kit-search',
        ROOT / 'vanilla' / 'tmenu',
    ]

    for script in scripts_to_check:
        assert script.exists(), f"Expected script {script} does not exist"
        res = sp.run([BASH, '-n', str(script)], capture_output=True, text=True)
        assert res.returncode == 0, f"Syntax check failed for {script}:\n{res.stderr}"
    log("Tier 1 passed: All shell scripts passed syntax checks.")


# ============================================================================
# Tier 2: Clean-HOME Isolated Install & Uninstall Cycle + set -u verification
# ============================================================================
def check_clean_home_and_nounset():
    log("Tier 2: Testing clean-HOME install/uninstall cycles and set -u (nounset)...")
    with tempfile.TemporaryDirectory(prefix='shell-kit-portable-home-') as tmp_home_str:
        tmp_home = Path(tmp_home_str)
        # Prepopulate with a pre-existing .bashrc and .bash_profile containing user content
        (tmp_home / '.bashrc').write_text("# User existing bashrc\nalias myuseralias='echo hi'\n")
        (tmp_home / '.bash_profile').write_text("# User existing profile\nexport MY_VAR=1\n")
        initial_bashrc = (tmp_home / '.bashrc').read_bytes()
        initial_profile = (tmp_home / '.bash_profile').read_bytes()

        env = dict(os.environ, HOME=str(tmp_home))
        for key in ('TMUX', 'TMUX_PANE', 'BASH_ENV', 'ENV'):
            env.pop(key, None)

        # 1. Run install.sh in vanilla mode
        install_res = sp.run(
            [BASH, str(ROOT / 'install.sh'), '--components', 'helpers,references,tmux,vim,skill', '--mode', 'vanilla', '--yes'],
            env=env, capture_output=True, text=True
        )
        assert install_res.returncode == 0, f"install.sh failed:\nstdout: {install_res.stdout}\nstderr: {install_res.stderr}"

        # Verify managed block is present in rc files
        for rc_file in (tmp_home / '.bashrc', tmp_home / '.bash_profile', tmp_home / '.zshrc'):
            if rc_file.exists():
                content = rc_file.read_bytes()
                assert b'BEGIN SHELL-KIT' in content.upper(), f"Managed block missing from {rc_file.name}"
                assert b'END SHELL-KIT' in content.upper(), f"End marker missing from {rc_file.name}"

        # 2. Spawn subshells with nounset (set -u) in both non-interactive and interactive modes
        # Non-interactive sourcing
        non_interactive_cmd = 'set -u; . "$HOME/.bashrc"; . "$HOME/.bash_profile"; exit 0'
        res_non_interactive = sp.run(
            [BASH, '--noprofile', '--norc', '-c', non_interactive_cmd],
            env=env, capture_output=True, text=True
        )
        assert res_non_interactive.returncode == 0, (
            f"Non-interactive bash with set -u failed:\nstdout: {res_non_interactive.stdout}\nstderr: {res_non_interactive.stderr}"
        )

        # Interactive subshell sourcing
        interactive_cmd = 'set -u; . "$HOME/.bashrc"; . "$HOME/.bash_profile"; type configs >/dev/null; type cheat >/dev/null; exit 0'
        res_interactive = sp.run(
            [BASH, '--noprofile', '--norc', '-i', '-c', interactive_cmd],
            env=env, capture_output=True, text=True
        )
        assert res_interactive.returncode == 0, (
            f"Interactive bash with set -u failed:\nstdout: {res_interactive.stdout}\nstderr: {res_interactive.stderr}"
        )

        # 3. Run uninstaller
        uninstall_res = sp.run(
            [BASH, str(ROOT / 'install.sh'), '--uninstall', '--yes'],
            env=env, capture_output=True, text=True
        )
        assert uninstall_res.returncode == 0, f"Uninstaller failed:\nstdout: {uninstall_res.stdout}\nstderr: {uninstall_res.stderr}"

        # Verify clean restoration: managed blocks removed, original user content intact
        for rc_file in (tmp_home / '.bashrc', tmp_home / '.bash_profile'):
            content = rc_file.read_bytes()
            assert b'SHELL-KIT' not in content.upper(), f"Managed block still present in {rc_file.name} after uninstall"
        assert (tmp_home / '.bashrc').read_bytes() == initial_bashrc, "User .bashrc was not cleanly restored"
        assert (tmp_home / '.bash_profile').read_bytes() == initial_profile, "User .bash_profile was not cleanly restored"

        # Verify symlinks were removed or clean
        runtime_bin = tmp_home / '.local' / 'share' / 'shell-kit-runtime' / 'bin'
        if runtime_bin.exists():
            for link in runtime_bin.iterdir():
                assert not link.is_symlink() or link.resolve().exists(), f"Dangling or leftover symlink {link}"

    log("Tier 2 passed: Clean-HOME install/uninstall cycle and nounset checks verified.")


# ============================================================================
# Tier 3: Missing Optional Tool Fallbacks
# ============================================================================
def check_optional_tool_fallbacks():
    log("Tier 3: Verifying graceful fallbacks when optional tools (rg, fzf, bat, less) are missing...")
    with tempfile.TemporaryDirectory(prefix='shell-kit-fallback-') as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        home = tmp_dir / 'home'
        home.mkdir()
        restricted_bin = tmp_dir / 'bin'
        restricted_bin.mkdir()

        # Provide only standard POSIX / base utilities, explicitly omitting rg, fzf, bat, less
        essential_tools = [
            'bash', 'awk', 'cat', 'cmp', 'cp', 'date', 'dirname', 'ln',
            'mkdir', 'mktemp', 'mv', 'readlink', 'rm', 'stty', 'tail',
            'chmod', 'grep', 'find', 'sort', 'tr', 'sed', 'head'
        ]
        for tool in essential_tools:
            tool_path = shutil.which(tool)
            if tool_path:
                (restricted_bin / tool).symlink_to(tool_path)

        assert not (restricted_bin / 'rg').exists()
        assert not (restricted_bin / 'fzf').exists()
        assert not (restricted_bin / 'bat').exists()
        assert not (restricted_bin / 'less').exists()

        env = dict(os.environ, HOME=str(home), PATH=str(restricted_bin))
        for key in ('TMUX', 'TMUX_PANE', 'BASH_ENV', 'ENV'):
            env.pop(key, None)

        # 1. Install vanilla components (helpers, references, skill) under restricted PATH
        install_res = sp.run(
            [BASH, str(ROOT / 'install.sh'), '--components', 'helpers,references,skill', '--mode', 'vanilla', '--yes'],
            env=env, capture_output=True, text=True
        )
        assert install_res.returncode == 0, f"Install under restricted PATH failed: {install_res.stderr}"

        # 2. Test shell-kit-search sfind (must fall back to grep when rg is absent)
        sample_file = home / 'test_search.txt'
        sample_file.write_text("line1\nsearch_target_pattern\nline3\n")
        search_bin = ROOT / 'vanilla' / 'shell-kit-search'
        res_sfind = sp.run(
            [BASH, str(search_bin), 'sfind', 'search_target_pattern', str(home)],
            env=env, capture_output=True, text=True
        )
        assert res_sfind.returncode == 0, f"sfind fallback to grep failed: {res_sfind.stderr}"
        assert 'search_target_pattern' in res_sfind.stdout, f"Pattern not found in output: {res_sfind.stdout}"

        # 3. Test cheat fallback when less is absent (must fall back to cat)
        cheat_bin = ROOT / 'vanilla' / 'cheat'
        res_cheat = sp.run(
            [BASH, str(cheat_bin), 'tmux'],
            env=env, capture_output=True, text=True
        )
        assert res_cheat.returncode == 0, f"cheat fallback to cat failed: {res_cheat.stderr}"
        expected_sheet = (ROOT / 'sheets' / 'tmux.md').read_text()
        assert res_cheat.stdout == expected_sheet, "cheat output does not match expected markdown content"

        # 4. Test tmenu fallback when tmux has no sessions (must print message and exit 0)
        tmenu_bin = ROOT / 'vanilla' / 'tmenu'
        mock_tmux = restricted_bin / 'tmux'
        mock_tmux.write_text('#!/bin/sh\nexit 1\n')
        mock_tmux.chmod(0o755)
        res_tmenu = sp.run([BASH, str(tmenu_bin)], env=env, capture_output=True, text=True)
        assert res_tmenu.returncode == 0, f"tmenu failed with no sessions: {res_tmenu.stderr}"
        assert 'No sessions yet' in res_tmenu.stdout, f"Unexpected tmenu output: {res_tmenu.stdout}"
        mock_tmux.unlink()

    log("Tier 3 passed: All missing optional tool fallbacks operated gracefully without error.")


# ============================================================================
# Tier 4: Idempotency Verification
# ============================================================================
def hash_directory(directory: Path):
    """Compute sha256 hashes of all regular files in directory tree."""
    hashes = {}
    for path in sorted(directory.rglob('*')):
        if path.is_file() and not path.is_symlink():
            rel = str(path.relative_to(directory))
            if 'backups' in rel:
                continue
            hasher = hashlib.sha256()
            hasher.update(path.read_bytes())
            hashes[rel] = hasher.hexdigest()
        elif path.is_symlink():
            rel = str(path.relative_to(directory))
            hashes[rel] = f"symlink->{os.readlink(path)}"
    return hashes


def check_idempotency():
    log("Tier 4: Verifying install idempotency across consecutive runs...")
    with tempfile.TemporaryDirectory(prefix='shell-kit-idempotency-') as tmp_home_str:
        tmp_home = Path(tmp_home_str)
        (tmp_home / '.bashrc').write_text("# Existing user bashrc\n")
        (tmp_home / '.zshrc').write_text("# Existing user zshrc\n")

        env = dict(os.environ, HOME=str(tmp_home))
        for key in ('TMUX', 'TMUX_PANE', 'BASH_ENV', 'ENV'):
            env.pop(key, None)

        cmd = [BASH, str(ROOT / 'install.sh'), '--components', 'helpers,references,tmux,vim,skill', '--mode', 'vanilla', '--yes']

        # First install run
        res1 = sp.run(cmd, env=env, capture_output=True, text=True)
        assert res1.returncode == 0, f"First install failed: {res1.stderr}"
        hashes_after_first = hash_directory(tmp_home)

        # Second install run (immediate consecutive rerun)
        res2 = sp.run(cmd, env=env, capture_output=True, text=True)
        assert res2.returncode == 0, f"Second install failed: {res2.stderr}"
        hashes_after_second = hash_directory(tmp_home)

        # Compare hashes
        assert hashes_after_first == hashes_after_second, (
            f"Idempotency failure: files changed between runs!\n"
            f"Diff: {set(hashes_after_first.items()) ^ set(hashes_after_second.items())}"
        )
    log("Tier 4 passed: Consecutive install runs are strictly idempotent.")


def main():
    log("Starting comprehensive portability and validation test suite...")
    check_shell_syntax()
    check_clean_home_and_nounset()
    check_optional_tool_fallbacks()
    check_idempotency()
    log("All 4 portability tiers passed successfully!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
