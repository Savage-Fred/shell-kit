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
import re
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
        ROOT / 'uninstall.sh',
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
# Tier 2: Clean-HOME Isolated Install & Uninstall Cycle + Safe Backups + Symlinks
# ============================================================================
def check_clean_home_and_nounset():
    log("Tier 2: Testing clean-HOME install/uninstall cycles, safe backups, symlink preservation, and set -u...")
    
    # Part A: AC2 - Clean temporary HOME without pre-existing dotfiles exits 0, subshells load cleanly
    with tempfile.TemporaryDirectory(prefix='shell-kit-clean-home-') as clean_home_str:
        clean_home = Path(clean_home_str)
        clean_env = dict(os.environ, HOME=str(clean_home))
        for key in ('TMUX', 'TMUX_PANE', 'BASH_ENV', 'ENV'):
            clean_env.pop(key, None)

        install_res = sp.run(
            [BASH, str(ROOT / 'install.sh'), '--components', 'helpers,references,tmux,vim,skill', '--mode', 'vanilla', '--yes'],
            env=clean_env, capture_output=True, text=True
        )
        assert install_res.returncode == 0, f"Clean HOME install failed:\nstdout: {install_res.stdout}\nstderr: {install_res.stderr}"

        # Subshell loads cleanly
        subshell_res = sp.run(
            [BASH, '--noprofile', '--norc', '-c', 'set -u; . "$HOME/.bashrc"; exit 0'],
            env=clean_env, capture_output=True, text=True
        )
        assert subshell_res.returncode == 0, f"Clean HOME subshell failed:\nstdout: {subshell_res.stdout}\nstderr: {subshell_res.stderr}"
        # No backups should be created when no pre-existing files existed
        backups_dir = clean_home / '.local/state/shell-kit/backups'
        assert not backups_dir.exists() or len(list(backups_dir.iterdir())) == 0, "Backup directory unexpectedly created in clean HOME"

    # Part B: Pre-existing dotfiles, symlink preservation, timestamped backups (AC1, AC3), and uninstall.sh
    with tempfile.TemporaryDirectory(prefix='shell-kit-portable-home-') as tmp_home_str:
        tmp_home = Path(tmp_home_str)
        dotfiles_dir = tmp_home / 'my_dotfiles'
        dotfiles_dir.mkdir()
        real_bashrc = dotfiles_dir / 'bashrc'
        real_bashrc.write_text("# User existing bashrc\nalias myuseralias='echo hi'\n")
        
        # Symlink ~/.bashrc -> ~/my_dotfiles/bashrc (symlink preservation test)
        symlinked_bashrc = tmp_home / '.bashrc'
        symlinked_bashrc.symlink_to(real_bashrc)
        
        (tmp_home / '.bash_profile').write_text("# User existing profile\nexport MY_VAR=1\n")
        initial_bashrc = real_bashrc.read_bytes()
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

        # AC1: Verify timestamped backup exists under ~/.local/state/shell-kit/backups/YYYYMMDD_HHMMSS/
        backups_dir = tmp_home / '.local/state/shell-kit/backups'
        assert backups_dir.exists(), "Backups directory was not created"
        backup_runs = sorted(path.name for path in backups_dir.iterdir())
        assert len(backup_runs) == 1, f"Expected exactly 1 backup directory, found {backup_runs}"
        backup_dir = backups_dir / backup_runs[0]
        assert re.match(r'^\d{8}_\d{6}$', backup_dir.name), f"Backup dir {backup_dir.name} is not YYYYMMDD_HHMMSS format"
        
        # Verify manifest.txt, checksums.sha256, and non-empty backed up files
        manifest = backup_dir / 'manifest.txt'
        checksums = backup_dir / 'checksums.sha256'
        assert manifest.is_file() and manifest.stat().st_size > 0, "Manifest missing or empty"
        assert checksums.is_file() and checksums.stat().st_size > 0, "Checksums file missing or empty"
        backed_files = [f for f in backup_dir.iterdir() if f.is_file() and f.name not in ('manifest.txt', 'checksums.sha256', 'files.tsv')]
        assert len(backed_files) > 0, "No backed up files found in backup dir"
        for bf in backed_files:
            assert bf.stat().st_size > 0, f"Backed up file {bf} is empty"

        # Verify symlink preservation: ~/.bashrc must remain a symlink pointing to real_bashrc
        assert symlinked_bashrc.is_symlink(), "Installer replaced a user symlink with a regular file"
        assert symlinked_bashrc.resolve() == real_bashrc.resolve(), "Symlink destination changed"
        assert b'BEGIN SHELL-KIT' in real_bashrc.read_bytes(), "Managed block missing from symlink target"
        assert b'alias myuseralias=' in real_bashrc.read_bytes(), "Pre-existing content lost in symlink target"

        # Verify managed block is present in rc files
        for rc_file in (real_bashrc, tmp_home / '.bash_profile'):
            content = rc_file.read_bytes()
            assert b'BEGIN SHELL-KIT' in content.upper(), f"Managed block missing from {rc_file.name}"
            assert b'END SHELL-KIT' in content.upper(), f"End marker missing from {rc_file.name}"

        # 2. Spawn subshells with nounset (set -u) in both non-interactive and interactive modes
        non_interactive_cmd = 'set -u; . "$HOME/.bashrc"; . "$HOME/.bash_profile"; exit 0'
        res_non_interactive = sp.run(
            [BASH, '--noprofile', '--norc', '-c', non_interactive_cmd],
            env=env, capture_output=True, text=True
        )
        assert res_non_interactive.returncode == 0, (
            f"Non-interactive bash with set -u failed:\nstdout: {res_non_interactive.stdout}\nstderr: {res_non_interactive.stderr}"
        )

        interactive_cmd = 'set -u; . "$HOME/.bashrc"; . "$HOME/.bash_profile"; type configs >/dev/null; type cheat >/dev/null; exit 0'
        res_interactive = sp.run(
            [BASH, '--noprofile', '--norc', '-i', '-c', interactive_cmd],
            env=env, capture_output=True, text=True
        )
        assert res_interactive.returncode == 0, (
            f"Interactive bash with set -u failed:\nstdout: {res_interactive.stdout}\nstderr: {res_interactive.stderr}"
        )

        # AC3: Consecutive re-run idempotency
        rerun_res = sp.run(
            [BASH, str(ROOT / 'install.sh'), '--components', 'helpers,references,tmux,vim,skill', '--mode', 'vanilla', '--yes'],
            env=env, capture_output=True, text=True
        )
        assert rerun_res.returncode == 0, f"Consecutive rerun failed:\n{rerun_res.stderr}"
        assert sorted(path.name for path in backups_dir.iterdir()) == backup_runs, "Rerun created unnecessary backup"
        assert symlinked_bashrc.is_symlink(), "Rerun broke symlink"

        # 3. Run uninstaller via uninstall.sh
        uninstall_res = sp.run(
            [BASH, str(ROOT / 'uninstall.sh'), '--yes'],
            env=env, capture_output=True, text=True
        )
        assert uninstall_res.returncode == 0, f"uninstall.sh failed:\nstdout: {uninstall_res.stdout}\nstderr: {uninstall_res.stderr}"

        # Verify clean restoration: symlink preserved, managed blocks removed, original user content intact
        assert symlinked_bashrc.is_symlink(), "Uninstaller replaced symlink with regular file"
        assert symlinked_bashrc.resolve() == real_bashrc.resolve(), "Symlink destination changed on uninstall"
        for rc_file in (real_bashrc, tmp_home / '.bash_profile'):
            content = rc_file.read_bytes()
            assert b'SHELL-KIT' not in content.upper(), f"Managed block still present in {rc_file.name} after uninstall"
        assert real_bashrc.read_bytes() == initial_bashrc, "User .bashrc was not cleanly restored"
        assert (tmp_home / '.bash_profile').read_bytes() == initial_profile, "User .bash_profile was not cleanly restored"

        # Verify symlinks were removed from runtime bin
        runtime_bin = tmp_home / '.local' / 'share' / 'shell-kit-runtime' / 'bin'
        if runtime_bin.exists():
            for link in runtime_bin.iterdir():
                assert not link.is_symlink() or link.resolve().exists(), f"Dangling or leftover symlink {link}"

    log("Tier 2 passed: Clean-HOME install/uninstall cycle, safe backups, symlink preservation, and nounset checks verified.")


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
        dotfiles_dir = tmp_home / 'dotfiles'
        dotfiles_dir.mkdir()
        real_bashrc = dotfiles_dir / 'bashrc'
        real_bashrc.write_text("# Existing user bashrc in dotfiles\n")
        (tmp_home / '.bashrc').symlink_to(real_bashrc)
        (tmp_home / '.zshrc').write_text("# Existing user zshrc\n")

        env = dict(os.environ, HOME=str(tmp_home))
        for key in ('TMUX', 'TMUX_PANE', 'BASH_ENV', 'ENV'):
            env.pop(key, None)

        cmd = [BASH, str(ROOT / 'install.sh'), '--components', 'helpers,references,tmux,vim,skill', '--mode', 'vanilla', '--yes']

        # First install run
        res1 = sp.run(cmd, env=env, capture_output=True, text=True)
        assert res1.returncode == 0, f"First install failed: {res1.stderr}"
        assert (tmp_home / '.bashrc').is_symlink(), "First run clobbered symlink"
        hashes_after_first = hash_directory(tmp_home)

        # Second install run (immediate consecutive rerun)
        res2 = sp.run(cmd, env=env, capture_output=True, text=True)
        assert res2.returncode == 0, f"Second install failed: {res2.stderr}"
        assert (tmp_home / '.bashrc').is_symlink(), "Second run clobbered symlink"
        hashes_after_second = hash_directory(tmp_home)

        # Compare hashes (strictly 0 diff on rerun)
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
