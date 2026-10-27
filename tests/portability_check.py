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


def main():
    log("Starting comprehensive portability and validation test suite...")
    check_shell_syntax()
    check_clean_home_and_nounset()
    check_optional_tool_fallbacks()
    check_idempotency()
    check_bash32_nounset_array_expansion()
    check_batcat_detection_logic()
    check_portable_path_resolution()
    log("All 7 portability tiers passed successfully!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
