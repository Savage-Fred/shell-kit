#!/usr/bin/env python3
"""Automated validation and portability test suite for shell-kit.

Satisfies Requirement R2 (cross-OS/cross-distro compatibility):
1. Shell syntax validation (bash -n on all core scripts).
2. Clean-HOME isolated install & uninstall cycle with set -u (nounset) subshell verification.
3. Missing optional tool fallbacks (graceful operation when optional tools like rg, fzf, bat, less are missing).
4. Idempotency verification (consecutive runs produce identical file hashes).
5. Bash 3.2 nounset empty array expansion verification (${arr[@]+"${arr[@]}"}).
6. batcat vs bat detection and fallback logic across distributions.
7. Portable path resolution on symlinks, spaces, and environments without GNU readlink -f.
8. Graceful degradation when optional dependencies (rg, fd, fzf, bat, eza, starship) are missing.
9. Shell startup latency benchmark (<15ms), non-interactive hygiene (0 bytes stdout/stderr), and tmux hook hardening.
"""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess as sp
import sys
import tempfile
import time

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
        ROOT / 'helpers' / 'functions.sh',
        ROOT / 'helpers' / 'aliases.sh',
        ROOT / 'helpers' / 'prompt.sh',
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


# ============================================================================
# Tier 5: Bash 3.2 set -u (nounset) Array Expansion Verification
# ============================================================================
def check_bash32_nounset_array_expansion():
    log("Tier 5: Testing empty array expansion under set -u simulating Bash 3.2 nounset...")

    # 1. Behavior verification of guarded array expansion vs bare array expansion:
    # Under Bash 3.2, bare "${empty_arr[@]}" raises an unbound variable error when set -u is enabled.
    # The portable pattern ${arr[@]+"${arr[@]}"} safely evaluates to empty without error.
    script_guarded = '''
    set -u
    empty_arr=()
    count=0
    for item in ${empty_arr[@]+"${empty_arr[@]}"}; do
        count=$((count + 1))
    done
    [ "$count" -eq 0 ] || exit 1

    populated_arr=("first item with spaces" "second item")
    count=0
    for item in ${populated_arr[@]+"${populated_arr[@]}"}; do
        count=$((count + 1))
    done
    [ "$count" -eq 2 ] || exit 2
    exit 0
    '''
    res = sp.run([BASH, '-c', script_guarded], capture_output=True, text=True)
    assert res.returncode == 0, f"Guarded array expansion behavior check failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"

    # 2. Static AST / pattern check: no repo script contains bare "${arr[@]}" under set -u
    scripts_to_audit = [
        ROOT / 'install.sh',
        ROOT / 'uninstall.sh',
        ROOT / 'bin' / 'cheat',
        ROOT / 'helpers' / 'functions.sh',
        ROOT / 'helpers' / 'aliases.sh',
        ROOT / 'helpers' / 'prompt.sh',
        ROOT / 'vanilla' / 'cheat',
        ROOT / 'vanilla' / 'configs',
        ROOT / 'vanilla' / 'shell-kit-search',
        ROOT / 'vanilla' / 'tmenu',
        ROOT / 'integrations' / 'shell.sh',
    ]

    bare_array_regex = re.compile(r'(?<!\+)"\$\{([a-zA-Z0-9_]+)\[@\]\}"')
    for script in scripts_to_audit:
        assert script.is_file(), f"Script {script} not found"
        content = script.read_text()
        matches = bare_array_regex.findall(content)
        assert not matches, f"Bare array expansion found in {script.name}: {matches}. Must use ${{arr[@]+\"${{arr[@]}}\"}} for Bash 3.2 portability."

    # 3. Dynamic test: Execute install.sh, configs, and shell-kit-search under set -u with empty inputs
    with tempfile.TemporaryDirectory(prefix='shell-kit-nounset-') as tmp_dir_str:
        tmp_home = Path(tmp_dir_str)
        env = dict(os.environ, HOME=str(tmp_home))
        for key in ('TMUX', 'TMUX_PANE', 'BASH_ENV', 'ENV'):
            env.pop(key, None)

        # install.sh --dry-run under set -u
        res_install = sp.run(
            [BASH, '-u', str(ROOT / 'install.sh'), '--components', 'helpers,references', '--mode', 'vanilla', '--dry-run'],
            env=env, capture_output=True, text=True
        )
        assert res_install.returncode == 0, f"install.sh failed under set -u:\n{res_install.stderr}"

        # vanilla/configs under set -u
        res_configs = sp.run(
            [BASH, '-u', str(ROOT / 'vanilla' / 'configs'), 'deps', '-d', str(tmp_home)],
            env=env, capture_output=True, text=True
        )
        assert res_configs.returncode == 0, f"configs failed under set -u:\n{res_configs.stderr}"

        # vanilla/shell-kit-search under set -u
        res_search = sp.run(
            [BASH, '-u', str(ROOT / 'vanilla' / 'shell-kit-search'), 'aliases', ''],
            input="alias ll='ls -l'\n",
            env=env, capture_output=True, text=True
        )
        assert res_search.returncode == 0, f"shell-kit-search failed under set -u:\n{res_search.stderr}"

    log("Tier 5 passed: Empty array expansion under set -u and Bash 3.2 nounset compatibility verified.")


# ============================================================================
# Tier 6: batcat vs bat Fallback and Detection Verification
# ============================================================================
def check_batcat_detection_logic():
    log("Tier 6: Testing batcat vs bat detection logic across Linux/Debian/macOS environments...")
    with tempfile.TemporaryDirectory(prefix='shell-kit-bat-test-') as tmp_str:
        tmp_dir = Path(tmp_str)
        mock_bin = tmp_dir / 'bin'
        mock_bin.mkdir()
        test_file = tmp_dir / 'sample.md'
        test_file.write_text("# Test Document\nLine 2 content\nLine 3 content\n")

        # Base minimal tools required by shell scripts
        for tool in ('bash', 'sh', 'cat', 'less', 'awk', 'grep', 'sed'):
            p = shutil.which(tool)
            if p:
                (mock_bin / tool).symlink_to(p)

        search_script = ROOT / 'vanilla' / 'shell-kit-search'

        # Case A: Only 'bat' is available (macOS / Arch / Fedora / standard packaging)
        mock_bat = mock_bin / 'bat'
        mock_bat.write_text('#!/bin/sh\nprintf "BAT_INVOKED: %s\\n" "$*"\n')
        mock_bat.chmod(0o755)

        env_bat = dict(os.environ, PATH=str(mock_bin))
        res_bat = sp.run([BASH, str(search_script), 'preview', str(test_file)], env=env_bat, capture_output=True, text=True)
        assert res_bat.returncode == 0, f"preview with bat failed: {res_bat.stderr}"
        assert 'BAT_INVOKED:' in res_bat.stdout, f"Expected bat invocation, got: {res_bat.stdout}"
        mock_bat.unlink()

        # Case B: Only 'batcat' is available (Debian / Ubuntu / Raspbian packaging quirk)
        mock_batcat = mock_bin / 'batcat'
        mock_batcat.write_text('#!/bin/sh\nprintf "BATCAT_INVOKED: %s\\n" "$*"\n')
        mock_batcat.chmod(0o755)

        env_batcat = dict(os.environ, PATH=str(mock_bin))
        res_batcat = sp.run([BASH, str(search_script), 'preview', str(test_file)], env=env_batcat, capture_output=True, text=True)
        assert res_batcat.returncode == 0, f"preview with batcat failed: {res_batcat.stderr}"
        assert 'BATCAT_INVOKED:' in res_batcat.stdout, f"Expected batcat invocation, got: {res_batcat.stdout}"

        # Case C: Both 'bat' and 'batcat' are present - 'bat' takes precedence
        mock_bat = mock_bin / 'bat'
        mock_bat.write_text('#!/bin/sh\nprintf "BAT_PRIMARY: %s\\n" "$*"\n')
        mock_bat.chmod(0o755)

        env_both = dict(os.environ, PATH=str(mock_bin))
        res_both = sp.run([BASH, str(search_script), 'preview', str(test_file)], env=env_both, capture_output=True, text=True)
        assert res_both.returncode == 0, f"preview with both failed: {res_both.stderr}"
        assert 'BAT_PRIMARY:' in res_both.stdout, f"Expected bat preference over batcat, got: {res_both.stdout}"

        # Case D: Neither is available - falls back cleanly to cat / less
        mock_bat.unlink()
        mock_batcat.unlink()
        env_none = dict(os.environ, PATH=str(mock_bin))
        res_none = sp.run([BASH, str(search_script), 'preview', str(test_file)], env=env_none, capture_output=True, text=True)
        assert res_none.returncode == 0, f"preview fallback failed: {res_none.stderr}"
        assert test_file.read_text() in res_none.stdout or res_none.stdout == test_file.read_text(), (
            f"Expected file contents on fallback, got: {res_none.stdout}"
        )

    log("Tier 6 passed: batcat vs bat detection logic verified successfully.")


# ============================================================================
# Tier 7: Portable Path Resolution (Symlinks, Paths with Spaces, No readlink -f)
# ============================================================================
def check_portable_path_resolution():
    log("Tier 7: Testing portable path resolution on symlinks, paths with spaces, and without GNU readlink -f...")
    with tempfile.TemporaryDirectory(prefix='shell-kit-path-res-') as tmp_str:
        tmp_dir = Path(tmp_str)

        # 1. Test multi-level symlink resolution with spaces in path names
        dir_with_spaces = tmp_dir / "target directory with spaces"
        dir_with_spaces.mkdir()
        sub_dir = dir_with_spaces / "sub dir with spaces"
        sub_dir.mkdir()
        real_file = sub_dir / "real target config.txt"
        real_file.write_text("CONFIG_DATA=1\n")

        # Chain: link_c -> link_b -> link_a -> real_file
        link_dir = tmp_dir / "link directory with spaces"
        link_dir.mkdir()
        link_a = link_dir / "symlink_a"
        link_a.symlink_to(real_file)
        link_b = link_dir / "symlink_b"
        link_b.symlink_to(link_a)
        link_c = link_dir / "symlink_c with spaces"
        link_c.symlink_to(link_b)

        # Portable resolution script mimicking resolve() from install.sh
        resolve_test_sh = f'''
        resolve() {{
            local path=$1 dest count=0 dir base
            while [ -L "$path" ]; do
                count=$((count + 1)); [ "$count" -le 40 ] || exit 42
                dest=$(readlink "$path")
                case $dest in /*) path=$dest;; *) path=$(dirname "$path")/$dest;; esac
            done
            dir=$(dirname "$path")
            base=${{path##*/}}
            if [ -d "$dir" ]; then
                dir=$(cd -P -- "$dir" 2>/dev/null && pwd -P)
                if [ "$dir" = "/" ]; then path="/$base"
                else path="$dir/$base"; fi
            fi
            printf '%s\\n' "$path"
        }}
        resolve "{link_c}"
        '''
        res = sp.run([BASH, '-c', resolve_test_sh], capture_output=True, text=True)
        assert res.returncode == 0, f"Resolution script failed:\n{res.stderr}"
        resolved_path = res.stdout.strip()
        assert Path(resolved_path) == real_file.resolve(), (
            f"Resolved path '{resolved_path}' does not match real file '{real_file.resolve()}'"
        )

        # 2. Verify scripts executed via symlinks in paths with spaces resolve their root correctly
        space_bin_dir = tmp_dir / "bin with spaces"
        space_bin_dir.mkdir()

        # Symlink install.sh
        symlinked_installer = space_bin_dir / "install_symlink.sh"
        symlinked_installer.symlink_to(ROOT / "install.sh")
        res_inst = sp.run(
            [BASH, str(symlinked_installer), '--mode', 'vanilla', '--dry-run'],
            capture_output=True, text=True
        )
        assert res_inst.returncode == 0, f"Symlinked install.sh in path with spaces failed:\n{res_inst.stderr}"

        # Symlink uninstall.sh
        symlinked_uninstaller = space_bin_dir / "uninstall_symlink.sh"
        symlinked_uninstaller.symlink_to(ROOT / "uninstall.sh")
        res_uninst = sp.run(
            [BASH, str(symlinked_uninstaller), '--dry-run'],
            capture_output=True, text=True
        )
        assert res_uninst.returncode == 0, f"Symlinked uninstall.sh in path with spaces failed:\n{res_uninst.stderr}"

        # Symlink vanilla/configs
        symlinked_configs = space_bin_dir / "configs_symlink"
        symlinked_configs.symlink_to(ROOT / "vanilla" / "configs")
        res_cfg = sp.run(
            [BASH, str(symlinked_configs), '--help'],
            capture_output=True, text=True
        )
        assert res_cfg.returncode == 0, f"Symlinked configs in path with spaces failed:\n{res_cfg.stderr}"
        assert 'Usage: configs' in res_cfg.stdout

        # 3. Environment where readlink -f / realpath fail (simulating macOS / BSD environment)
        mock_env_dir = tmp_dir / "strict_posix_bin"
        mock_env_dir.mkdir()
        strict_readlink = mock_env_dir / "readlink"
        strict_readlink.write_text('''#!/bin/sh
for arg in "$@"; do
    case $arg in
        -f|-m|-e)
            printf "readlink: illegal option -- %s\\n" "$arg" >&2
            exit 1 ;;
    esac
done
exec /bin/readlink "$@"
''')
        strict_readlink.chmod(0o755)

        for tool in ('bash', 'sh', 'cat', 'cmp', 'cp', 'date', 'dirname', 'grep', 'ln',
                     'mkdir', 'mktemp', 'mv', 'rm', 'stty', 'tail', 'chmod', 'find', 'sort', 'tr', 'sed', 'awk'):
            p = shutil.which(tool)
            if p:
                (mock_env_dir / tool).symlink_to(p)

        # Verify readlink -f indeed fails in this mock environment
        strict_env = dict(os.environ, PATH=str(mock_env_dir), HOME=str(tmp_dir / 'strict_home'))
        Path(strict_env['HOME']).mkdir()
        for key in ('TMUX', 'TMUX_PANE', 'BASH_ENV', 'ENV'):
            strict_env.pop(key, None)

        test_fail = sp.run([str(mock_env_dir / 'readlink'), '-f', str(real_file)], capture_output=True, text=True)
        assert test_fail.returncode != 0, "Mock readlink -f did not fail as expected"

        # Run install.sh under this strict environment (should succeed without using readlink -f)
        install_res = sp.run(
            [BASH, str(ROOT / 'install.sh'), '--components', 'helpers', '--mode', 'vanilla', '--yes'],
            env=strict_env, capture_output=True, text=True
        )
        assert install_res.returncode == 0, f"install.sh failed in environment without readlink -f:\n{install_res.stderr}"

    log("Tier 7 passed: Portable path resolution without GNU readlink -f across symlinks and spaces verified.")


# ============================================================================
# Tier 8: Missing Optional Dependency Graceful Degradation & Fallback Wrappers
# ============================================================================
def check_missing_optional_dependency_fallbacks():
    log("Tier 8: Testing graceful degradation when optional dependencies (rg, fd, fzf, bat, eza, starship) are absent...")
    with tempfile.TemporaryDirectory(prefix='shell-kit-fallbacks-tier8-') as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        home = tmp_dir / 'home'
        home.mkdir()
        restricted_bin = tmp_dir / 'restricted_bin'
        restricted_bin.mkdir()

        # Populate restricted_bin with only basic POSIX utilities
        essential_tools = [
            'bash', 'sh', 'awk', 'cat', 'cmp', 'cp', 'date', 'dirname', 'ln',
            'mkdir', 'mktemp', 'mv', 'readlink', 'rm', 'stty', 'tail',
            'chmod', 'grep', 'find', 'sort', 'tr', 'sed', 'head', 'python3'
        ]
        for tool in essential_tools:
            tool_path = shutil.which(tool)
            if tool_path:
                (restricted_bin / tool).symlink_to(tool_path)

        # Explicitly verify optional tools are absent
        for missing_tool in ('rg', 'fd', 'fdfind', 'fzf', 'bat', 'batcat', 'eza', 'starship', 'less'):
            assert not (restricted_bin / missing_tool).exists(), f"{missing_tool} should not exist in restricted_bin"

        env = dict(os.environ, HOME=str(home), PATH=str(restricted_bin))
        for key in ('TMUX', 'TMUX_PANE', 'BASH_ENV', 'ENV'):
            env.pop(key, None)

        test_files_dir = tmp_dir / 'test_files'
        test_files_dir.mkdir()
        (test_files_dir / 'alpha.txt').write_text("first line\ntarget_token_found\nthird line\n")
        (test_files_dir / 'beta.log').write_text("another file without match\n")
        sub_dir = test_files_dir / 'my_special_dir'
        sub_dir.mkdir()
        (sub_dir / 'nested.txt').write_text("nested text\n")

        # --------------------------------------------------------------------
        # 1. fif: Missing rg, fzf, bat/batcat falls back cleanly to grep -rn & pager
        # --------------------------------------------------------------------
        fif_script = f'''
        . "{ROOT}/helpers/functions.sh"
        fif "target_token_found" "{test_files_dir}"
        '''
        res_fif = sp.run([BASH, '-i', '-c', fif_script], env=env, capture_output=True, text=True)
        assert res_fif.returncode == 0, f"fif failed in restricted environment: {res_fif.stderr}"
        assert 'target_token_found' in res_fif.stdout, f"fif output did not contain matching line: {res_fif.stdout}"
        assert 'alpha.txt' in res_fif.stdout, f"fif output did not include filename: {res_fif.stdout}"

        # Test fif with non-matching pattern under set -e (must not crash)
        fif_no_match = f'''
        set -e
        . "{ROOT}/helpers/functions.sh"
        fif "completely_absent_string_xyz" "{test_files_dir}"
        '''
        res_fif_nomatch = sp.run([BASH, '-i', '-c', fif_no_match], env=env, capture_output=True, text=True)
        assert res_fif_nomatch.returncode == 0, f"fif crashed on no match: {res_fif_nomatch.stderr}"

        # --------------------------------------------------------------------
        # 2. sfind, dfind, pfind: Missing fd falls back cleanly to POSIX find
        # --------------------------------------------------------------------
        find_script = f'''
        set -e
        . "{ROOT}/helpers/functions.sh"
        echo "===SFIND==="
        sfind "alpha" "{test_files_dir}"
        echo "===DFIND==="
        dfind "special" "{test_files_dir}"
        echo "===PFIND==="
        pfind "nested" "{test_files_dir}"
        '''
        res_find = sp.run([BASH, '-i', '-c', find_script], env=env, capture_output=True, text=True)
        assert res_find.returncode == 0, f"find helpers failed when fd missing: {res_find.stderr}"
        out_find = res_find.stdout
        assert "alpha.txt" in out_find, f"sfind POSIX fallback failed: {out_find}"
        assert "my_special_dir" in out_find, f"dfind POSIX fallback failed: {out_find}"
        assert "nested.txt" in out_find, f"pfind POSIX fallback failed: {out_find}"

        # Test sfind, dfind, pfind with mock fd present
        mock_fd = restricted_bin / 'fd'
        mock_fd.write_text('#!/bin/sh\necho "MOCK_FD_INVOKED: $@"\n')
        mock_fd.chmod(0o755)

        mock_find_script = f'''
        . "{ROOT}/helpers/functions.sh"
        sfind "test" "{test_files_dir}"
        dfind "test" "{test_files_dir}"
        pfind "test" "{test_files_dir}"
        '''
        res_mock_find = sp.run([BASH, '-i', '-c', mock_find_script], env=env, capture_output=True, text=True)
        assert res_mock_find.returncode == 0, f"fd invocation failed: {res_mock_find.stderr}"
        assert res_mock_find.stdout.count("MOCK_FD_INVOKED") == 3, f"mock fd not called for all 3 functions: {res_mock_find.stdout}"
        mock_fd.unlink()

        # --------------------------------------------------------------------
        # 3. bin/tmenu: Missing fzf degrades cleanly without crashing or exiting 1
        # --------------------------------------------------------------------
        mock_tmux = restricted_bin / 'tmux'
        mock_tmux.write_text('''#!/bin/sh
if [ "$1" = "list-sessions" ]; then
    printf "s1\\twork_session\\t3 windows\\tdetached\\ns2\\tdev_session\\t1 windows\\tdetached\\n"
    exit 0
fi
echo "MOCK_TMUX_ACTION: $@"
''')
        mock_tmux.chmod(0o755)

        # 3a: Non-interactive execution (pipes/headless): prints session list and exits 0
        tmenu_bin = ROOT / 'bin' / 'tmenu'
        res_tmenu_headless = sp.run([sys.executable, str(tmenu_bin)], input="", env=env, capture_output=True, text=True)
        assert res_tmenu_headless.returncode == 0, f"tmenu failed when fzf missing: {res_tmenu_headless.stderr}"
        assert "work_session" in res_tmenu_headless.stdout, f"work_session not in tmenu output: {res_tmenu_headless.stdout}"
        assert "dev_session" in res_tmenu_headless.stdout, f"dev_session not in tmenu output: {res_tmenu_headless.stdout}"

        # 3b: Interactive selection via piped input: selecting 1 invokes attach-session
        res_tmenu_select = sp.run([sys.executable, str(tmenu_bin)], input="1\n", env=env, capture_output=True, text=True)
        assert res_tmenu_select.returncode == 0, f"tmenu selection failed: {res_tmenu_select.stderr}"
        assert "MOCK_TMUX_ACTION: attach-session -t s1" in res_tmenu_select.stdout, f"tmenu did not attach target session: {res_tmenu_select.stdout}"

        # 3c: Piped cancel: entering 'q' cancels and exits 0 cleanly
        res_tmenu_cancel = sp.run([sys.executable, str(tmenu_bin)], input="q\n", env=env, capture_output=True, text=True)
        assert res_tmenu_cancel.returncode == 0, f"tmenu cancellation failed: {res_tmenu_cancel.stderr}"
        mock_tmux.unlink()

        # --------------------------------------------------------------------
        # 4. vanilla/cheat & bin/cheat-enhanced: Missing fzf/less/bat degrade to cat
        # --------------------------------------------------------------------
        # 4a: vanilla/cheat with missing less and bat outputs plain markdown
        res_vcheat = sp.run([BASH, str(ROOT / 'vanilla' / 'cheat'), 'tmux'], env=env, capture_output=True, text=True)
        assert res_vcheat.returncode == 0, f"vanilla/cheat failed when less/bat absent: {res_vcheat.stderr}"
        expected_sheet = (ROOT / 'sheets' / 'tmux.md').read_text()
        assert res_vcheat.stdout == expected_sheet, "vanilla/cheat output did not match expected sheet content"

        # 4b: vanilla/cheat without arguments when fzf is missing degrades cleanly to 'list'
        res_vcheat_list = sp.run([BASH, str(ROOT / 'vanilla' / 'cheat')], env=env, capture_output=True, text=True)
        assert res_vcheat_list.returncode == 0, f"vanilla/cheat with no args failed: {res_vcheat_list.stderr}"
        assert res_vcheat_list.stdout.startswith("Sheets:"), f"vanilla/cheat did not fall back to list: {res_vcheat_list.stdout}"

        # 4c: bin/cheat-enhanced view with missing less degrades to plain output without error
        res_echeat = sp.run([sys.executable, str(ROOT / 'bin' / 'cheat-enhanced'), 'view', 'tmux'], env=env, capture_output=True, text=True)
        assert res_echeat.returncode == 0, f"bin/cheat-enhanced failed when less absent: {res_echeat.stderr}"
        assert "tmux" in res_echeat.stdout.lower(), "bin/cheat-enhanced did not produce expected output"

        # --------------------------------------------------------------------
        # 5. vanilla/shell-kit-search: Fallbacks for preview, dfind, and fif
        # --------------------------------------------------------------------
        search_bin = ROOT / 'vanilla' / 'shell-kit-search'
        # 5a: preview when bat and less are missing falls back to cat
        res_prev = sp.run([BASH, str(search_bin), 'preview', str(ROOT / 'sheets' / 'tmux.md'), '10'], env=env, capture_output=True, text=True)
        assert res_prev.returncode == 0, f"preview fallback to cat failed: {res_prev.stderr}"
        assert expected_sheet in res_prev.stdout or len(res_prev.stdout) > 0, "preview failed to output file content"

        # 5b: dfind when fd is missing falls back to find
        res_search_dfind = sp.run([BASH, str(search_bin), 'dfind', 'sheets', str(ROOT)], env=env, capture_output=True, text=True)
        assert res_search_dfind.returncode == 0, f"shell-kit-search dfind failed: {res_search_dfind.stderr}"
        assert "sheets" in res_search_dfind.stdout, f"sheets directory not found by dfind: {res_search_dfind.stdout}"

        # 5c: fif when rg is missing falls back to grep
        res_search_fif = sp.run([BASH, str(search_bin), 'fif', 'Prefix', str(ROOT / 'sheets' / 'tmux.md')], env=env, capture_output=True, text=True)
        assert res_search_fif.returncode == 0, f"shell-kit-search fif failed: {res_search_fif.stderr}"
        assert "Prefix" in res_search_fif.stdout, f"Prefix not found by fif: {res_search_fif.stdout}"

        # --------------------------------------------------------------------
        # 6. Prompt: Starship guard prevents command-not-found & sets fallback PS1
        # --------------------------------------------------------------------
        prompt_script = f'''
        set -u
        . "{ROOT}/helpers/prompt.sh"
        echo "PS1_EFFECTIVE=$PS1"
        '''
        res_prompt = sp.run([BASH, '-i', '-c', prompt_script], env=env, capture_output=True, text=True)
        assert res_prompt.returncode == 0, f"helpers/prompt.sh failed under set -u without starship: {res_prompt.stderr}"
        assert "starship: command not found" not in res_prompt.stderr, f"Starship error leaked: {res_prompt.stderr}"
        assert "PS1_EFFECTIVE=" in res_prompt.stdout and len(res_prompt.stdout.strip()) > len("PS1_EFFECTIVE="), "Fallback prompt was not set"

        # Test prompt when mock starship is present
        mock_starship = restricted_bin / 'starship'
        mock_starship.write_text('#!/bin/sh\nif [ "$1" = "init" ]; then echo "export STARSHIP_LOADED=1"; exit 0; fi\n')
        mock_starship.chmod(0o755)
        mock_prompt_script = f'''
        . "{ROOT}/helpers/prompt.sh"
        echo "STARSHIP_STATUS=${{STARSHIP_LOADED:-0}}"
        '''
        res_mock_prompt = sp.run([BASH, '-i', '-c', mock_prompt_script], env=env, capture_output=True, text=True)
        assert res_mock_prompt.returncode == 0, f"prompt failed with starship: {res_mock_prompt.stderr}"
        assert "STARSHIP_STATUS=1" in res_mock_prompt.stdout, f"starship init was not invoked: {res_mock_prompt.stdout}"
        mock_starship.unlink()

        # --------------------------------------------------------------------
        # 7. Directory Aliases: eza vs ls fallback logic
        # --------------------------------------------------------------------
        alias_script = f'''
        shopt -s expand_aliases
        . "{ROOT}/helpers/aliases.sh"
        alias ll
        alias l
        alias la
        '''
        res_alias = sp.run([BASH, '-i', '-c', alias_script], env=env, capture_output=True, text=True)
        assert res_alias.returncode == 0, f"aliases.sh failed when eza missing: {res_alias.stderr}"
        assert "ls -la" in res_alias.stdout, f"ll did not fall back to ls -la: {res_alias.stdout}"

        # Test directory aliases when mock eza is present
        mock_eza = restricted_bin / 'eza'
        mock_eza.write_text('#!/bin/sh\nexit 0\n')
        mock_eza.chmod(0o755)

        res_mock_alias = sp.run([BASH, '-i', '-c', alias_script], env=env, capture_output=True, text=True)
        assert res_mock_alias.returncode == 0, f"aliases.sh failed with eza present: {res_mock_alias.stderr}"
        assert "eza -la" in res_mock_alias.stdout, f"ll did not use eza when present: {res_mock_alias.stdout}"
        mock_eza.unlink()

    log("Tier 8 passed: Graceful degradation for optional dependencies (rg, fd, fzf, bat, eza, starship) verified.")


# ============================================================================
# Tier 9: Shell Startup Latency Benchmark & Non-Interactive Session Hardening
# ============================================================================
def check_startup_latency_and_noninteractive_hygiene():
    log("Tier 9: Testing startup latency benchmark, non-interactive hygiene, and tmux hook hardening...")

    scripts_to_verify = [
        ROOT / 'integrations' / 'shell.sh',
        ROOT / 'helpers' / 'functions.sh',
        ROOT / 'helpers' / 'aliases.sh',
        ROOT / 'helpers' / 'prompt.sh',
        ROOT / 'vanilla' / 'configs',
        ROOT / 'vanilla' / 'shell-kit-search',
    ]

    shells_to_test = [BASH]
    sh_bin = shutil.which('sh')
    if sh_bin and sh_bin != BASH:
        shells_to_test.append(sh_bin)

    with tempfile.TemporaryDirectory(prefix='shell-kit-tier9-') as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        env = dict(os.environ, HOME=str(tmp_dir))
        for key in ('TMUX', 'TMUX_PANE', 'BASH_ENV', 'ENV'):
            env.pop(key, None)

        # 1. Non-interactive hygiene: strictly 0 bytes stdout, 0 bytes stderr, exit 0 under set -u
        for script in scripts_to_verify:
            assert script.is_file(), f"Target script {script} not found"
            for shell in shells_to_test:
                # 1a. Sourced in non-interactive shell under set -u
                res_source = sp.run(
                    [shell, '-u', '-c', f'. "{script}"'],
                    env=env, capture_output=True, text=True
                )
                assert res_source.returncode == 0, (
                    f"Non-interactive sourcing of {script.name} with {shell} failed with exit {res_source.returncode}:\n"
                    f"stdout: {res_source.stdout}\nstderr: {res_source.stderr}"
                )
                assert res_source.stdout == "", (
                    f"Non-interactive sourcing of {script.name} with {shell} leaked stdout: {repr(res_source.stdout)}"
                )
                assert res_source.stderr == "", (
                    f"Non-interactive sourcing of {script.name} with {shell} leaked stderr: {repr(res_source.stderr)}"
                )

                # 1b. Direct execution in non-interactive shell under set -u (for rc/helper scripts)
                if script.name in ('shell.sh', 'functions.sh', 'aliases.sh', 'prompt.sh'):
                    res_exec = sp.run(
                        [shell, '-u', str(script)],
                        env=env, capture_output=True, text=True
                    )
                    assert res_exec.returncode == 0, (
                        f"Non-interactive direct execution of {script.name} with {shell} failed with exit {res_exec.returncode}:\n"
                        f"stdout: {res_exec.stdout}\nstderr: {res_exec.stderr}"
                    )
                    assert res_exec.stdout == "", (
                        f"Non-interactive direct execution of {script.name} with {shell} leaked stdout: {repr(res_exec.stdout)}"
                    )
                    assert res_exec.stderr == "", (
                        f"Non-interactive direct execution of {script.name} with {shell} leaked stderr: {repr(res_exec.stderr)}"
                    )

        # 2. Benchmark non-interactive startup latency over 20 iterations (< 15.0 ms mean)
        iterations = 20
        timings = []
        source_cmd = [BASH, '-c', f'. "{ROOT}/integrations/shell.sh"']
        # Warmup iteration
        sp.run(source_cmd, env=env, capture_output=True)

        for _ in range(iterations):
            t_start = time.perf_counter()
            res_bench = sp.run(source_cmd, env=env, capture_output=True, text=True)
            t_elapsed = time.perf_counter() - t_start
            assert res_bench.returncode == 0, f"Benchmark run failed:\n{res_bench.stderr}"
            assert res_bench.stdout == "", f"Benchmark run produced stdout: {res_bench.stdout}"
            assert res_bench.stderr == "", f"Benchmark run produced stderr: {res_bench.stderr}"
            timings.append(t_elapsed)

        mean_ms = (sum(timings) / len(timings)) * 1000.0
        log(f"Tier 9 Benchmark: non-interactive startup latency = {mean_ms:.3f} ms over {iterations} iterations (threshold < 15.0 ms)")
        assert mean_ms < 15.0, f"Non-interactive startup latency exceeds threshold: {mean_ms:.2f} ms >= 15.0 ms"

        # 3. Interactive startup functions properly and all helpers are available
        interactive_script = f'''
        . "{ROOT}/integrations/shell.sh"
        type fif
        type sfind
        type dfind
        type pfind
        type tn
        type ta
        type td
        type aliases
        type configs
        '''
        res_interactive = sp.run(
            [BASH, '--norc', '-i', '-c', interactive_script],
            env=env, capture_output=True, text=True
        )
        assert res_interactive.returncode == 0, (
            f"Interactive startup failed:\nstdout: {res_interactive.stdout}\nstderr: {res_interactive.stderr}"
        )
        for expected_helper in ('fif', 'sfind', 'dfind', 'pfind', 'tn', 'ta', 'td', 'aliases', 'configs'):
            assert f"{expected_helper} is a function" in res_interactive.stdout or f"{expected_helper}()" in res_interactive.stdout, (
                f"Helper {expected_helper} missing from interactive session:\n{res_interactive.stdout}"
            )

        # 4. Tmux hooks hardening: verify hooks withstand empty/detached client attributes
        tmux_conf = ROOT / 'integrations' / 'tmux.conf'
        assert tmux_conf.is_file(), "tmux.conf not found"
        tmux_content = tmux_conf.read_text()
        assert 'client_tty' in tmux_content
        assert '-n' in tmux_content and '#{client_tty}' in tmux_content, (
            "tmux.conf hooks must check for client_tty presence before executing cheat attach"
        )
        assert '|| true' in tmux_content, "tmux.conf hooks must include || true safeguard"

        # Test cheat-enhanced attach and cleanup with empty/detached client parameters
        res_attach_empty = sp.run(
            [sys.executable, str(ROOT / 'bin' / 'cheat-enhanced'), 'attach', '', ''],
            env=env, capture_output=True, text=True
        )
        assert res_attach_empty.returncode == 0, f"cheat-enhanced attach with empty args crashed:\n{res_attach_empty.stderr}"
        assert res_attach_empty.stderr == "", f"cheat-enhanced attach with empty args leaked error:\n{res_attach_empty.stderr}"

        res_cleanup_empty = sp.run(
            [sys.executable, str(ROOT / 'bin' / 'cheat-enhanced'), 'cleanup', ''],
            env=env, capture_output=True, text=True
        )
        assert res_cleanup_empty.returncode == 0, f"cheat-enhanced cleanup with empty arg crashed:\n{res_cleanup_empty.stderr}"
        assert res_cleanup_empty.stderr == "", f"cheat-enhanced cleanup with empty arg leaked error:\n{res_cleanup_empty.stderr}"

        # Test vanilla/cheat attach and cleanup
        res_vcheat_attach = sp.run(
            [BASH, str(ROOT / 'vanilla' / 'cheat'), 'attach'],
            env=env, capture_output=True, text=True
        )
        assert res_vcheat_attach.returncode == 0, f"vanilla/cheat attach failed: {res_vcheat_attach.stderr}"

        res_vcheat_cleanup = sp.run(
            [BASH, str(ROOT / 'vanilla' / 'cheat'), 'cleanup'],
            env=env, capture_output=True, text=True
        )
        assert res_vcheat_cleanup.returncode == 0, f"vanilla/cheat cleanup failed: {res_vcheat_cleanup.stderr}"

    log("Tier 9 passed: Shell startup latency benchmark, non-interactive hygiene, and tmux hook resilience verified.")


def main():
    log("Starting comprehensive portability and validation test suite...")
    check_shell_syntax()
    check_clean_home_and_nounset()
    check_optional_tool_fallbacks()
    check_idempotency()
    check_bash32_nounset_array_expansion()
    check_batcat_detection_logic()
    check_portable_path_resolution()
    check_missing_optional_dependency_fallbacks()
    check_startup_latency_and_noninteractive_hygiene()
    log("All 9 portability tiers passed successfully!")
    return 0


if __name__ == '__main__':
    sys.exit(main())

