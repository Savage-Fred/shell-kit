<img src="assets/sheila.svg" alt="Sheila the koala" width="120">

# Sheila's shell-kit

A saved home for small, reusable terminal tools. Sheila keeps the shortcuts
beside your work so you can stop looking them up.

Start with `bash install.sh`. Choose only the components you want. New installs
default to vanilla mode: Bash and standard Unix tools, without Python or a package
manager. Enhanced rendering and automatic sidebars are optional.

## Start here

| Shortcut | Reference |
|---|---|
| **F1** | tmux |
| **F2** | Vim |
| **F3** | grep / ripgrep |
| **F4** | aliases and functions |

Press the same key to close. On a Mac, you may need **Fn + F1…F4**; the
terminal must send function keys instead of consuming them as app shortcuts.
The command equivalents always work: `cheat tmux`, `cheat vim`, `cheat grep`,
`cheat aliases`. Inside the editor, `:call ShellKitSheet('vim', 0)` is available.

In **enhanced mode**, tmux sheets stack on the **left**, work stays on the **right**, and opening
help keeps your typing focus. Move into help with `Ctrl-b ←`; use arrows,
PageUp/PageDown, `/` to search, `g` for the top, and `q` to close. The pager
starts at the top every time and renders Markdown and highlights fenced code with Rich. It follows tmux’s
light/dark client theme; set `CHEAT_THEME=light` or `dark` to override.
Links remain visible and can be opened using your terminal's link gesture.
The three-question tmux checklist is at the end of its sheet.

Standalone Vim/Neovim uses read-only Markdown splits with syntax highlighting,
keeps focus in the edited file, and closes its help when the last work window
quits. Vim inside tmux uses the shared left column. Its automatically opened
sheet closes when that Vim process exits; manually opened sheets stay open.
Closing the last work pane also removes the remaining help panes.

### Screen and client policy

This automatic policy applies to enhanced mode. Vanilla mode opens help only on
request: a tmux popup, a standalone pager, or an editor split/tab. With no `less`,
plain references print using `cat`; use `cheat NAME` when your terminal cannot
retain the printed output after a function-key widget returns.

| Situation | Automatic behavior | Manual help |
|---|---|---|
| Local desktop / Mac | tmux on attach, Vim on editor start | Left column |
| Known `macbook` remote profile | Same | Left column |
| `phone` or unidentified SSH client | Off | Available |
| Under 120 columns or 24 rows in tmux | Off | Temporary tmux window |
| Narrow standalone Vim | Off | Temporary help tab |
| Shell outside tmux | Off | Full-screen pager |

The column uses up to 80 characters, or 40% of window width. Rendered text
is capped at 80 columns. The pager wraps when narrowed; reopen a sheet after
widening it to reflow its text for the new width. Multiple sheets
split the existing help column; work-pane splits stay intact. If another sheet
would be too short to read, manual help uses a temporary tmux window instead.

**Recommendation:** keep one tmux session per task; use windows for different
activities and work-pane splits for closely related commands. Avoid cycling
whole-window layouts (`Ctrl-b Space`) while sidebars are open: tmux treats help
as ordinary panes and can rearrange them. Close the sheets, change the layout,
then reopen. No background layout daemon fights your choices.

Tmux layouts are shared, not private per attached client. The most recently
attached client's profile controls automatic help. A phone attaching removes
**automatic** sheets; it preserves manually opened ones. Simultaneous phone and
desktop users should use separate sessions if they need different layouts.

## Install / update

Run from your checkout (Bash 3.2 or newer):

```sh
bash install.sh
```

Use **arrow keys** to move, **Space** to select components, and **m** to switch
between vanilla and enhanced mode. **Enter** shows the proposed changes;
**y** applies them. **q**, Ctrl-C, or declining confirmation leaves configs alone.
The next run restores the saved selection. Unchecking a component removes its
managed integration. Installation applies the selected components individually.
Selecting tmux or an editor also selects References; unchecking References
unchecks those dependent integrations. The preview shows the complete selection.

| Component | Vanilla dependencies | Enhanced additions |
|---|---|---|
| Shell helpers / configs | Bash, awk, grep, find, sort, tr | None; uses rg when available |
| References / shell F1–F4 | Bash, cat; less optional | Python 3, less, private Rich environment |
| Tmux keys / session picker | References, tmux >=3.2 | fzf |
| Vim / Neovim references | References, Vim with scripting or Neovim | None |
| Agent reference skill | Standard file utilities | None |

The manager checks installed commands first. It reports whether Brew or apt-get
exists, but never invokes either, uses sudo, or installs system packages.
Use your machine's existing tools or leave unavailable components unchecked.
Enhanced mode shows any required private `venv`/pip setup in the confirmation
plan; that setup needs network access and a Python installation with `venv`.
Vanilla never invokes Python, pip, Brew or apt.

For an agent or a noninteractive terminal, preview a specific selection first:

```sh
bash install.sh --components helpers,references,skill --mode vanilla --dry-run
bash install.sh --components helpers,references,skill --mode vanilla --yes
bash install.sh --uninstall --dry-run
bash install.sh --uninstall --yes
```

`--components` is the complete desired selection, not an additive package list.
Required References are included automatically. Omitting other previously
selected components removes them. `--yes` explicitly approves
the displayed plan; without it, applying requires a terminal confirmation.
`--dry-run` does not change the checkout or installed configuration.

Managed source blocks preserve the surrounding configuration, dotfile symlinks,
and permissions. The installer checks all blocks for malformed markers and
validates destinations before changing configs. Backups and a `files.tsv` index
are kept in `~/.local/state/shell-kit/backups/install.*`; the index maps each
numbered backup to the original target path. Do not share these private backups.
Unexpected write failures can leave some components applied; retain the reported
backups, correct the filesystem problem, and rerun the same selection.

The manager respects `$ZDOTDIR`, `$XDG_CONFIG_HOME` for Neovim/tmux, an existing
`~/.vim/vimrc`, and Bash's active login profile. It records managed paths so a
later uninstall can remove its blocks even after config locations change.
Unrelated conflicting files/links are preserved and reported. Protected optional
skill discovery directories are skipped. Existing aliases and functions win.

Open a **new shell/editor** after saving. In a running tmux server, source the
active tmux configuration to load added bindings. Removing a component does not
unbind keys already loaded in a running shell/editor/server: they clear on its
next restart. Never kill a live server containing work just to refresh bindings.

The checkout stays in place, linked from `~/.local/share/shell-kit`. Update it
there, then rerun the manager. A previous `install.py` installation is recognized;
the new Bash installer replaces that installer and does not need it to migrate.

### Configure remote clients locally

Enhanced mode only: no machine names, addresses, SSH keys or network assumptions
are in this repo. `~/.config/shell-kit/clients.json` is an optional, **untracked** mapping
from SSH source address to `macbook`, `desktop` or `phone`. You can add the
current client without hardcoding an address in any shared file:

```sh
# Run in an SSH shell connected from the client you want to recognize.
python3 - <<'PY'
import json, os
from pathlib import Path
path = Path.home() / '.config/shell-kit/clients.json'
path.parent.mkdir(parents=True, exist_ok=True)
data = json.loads(path.read_text()) if path.exists() else {}
data[os.environ['SSH_CONNECTION'].split()[0]] = 'macbook'
path.write_text(json.dumps(data, indent=2) + '\n')
PY
cheat register
```

An explicit shell override is also supported:

```sh
export CHEAT_CLIENT=phone       # or macbook / desktop
cheat register                 # register before starting or attaching tmux
cheat profile                  # show effective profile
```

Addresses may change or be shared behind a jump host. In that case, use an
explicit profile in the remote terminal startup command, then start a login
shell. SSH doesn't provide a trustworthy device-type label automatically.
Unknown remote clients default to no automatic help. The registration uses the
outer shell's TTY, so a detached session doesn't retain the first client's
identity forever.

## Helpers

```sh
aliases grep            # loaded aliases/functions containing grep
aliases l               # names starting with l (single-letter query)
aliases ssh             # name or body contains ssh
sfind 'needle' .         # literal match, full paths, ±1 line, highlighting
dfind 'partial-name' .  # full matching directory paths
pfind 'needle' log.txt  # each match through the next blank line
configs                 # existing config candidates, listed once
configs deps -f ~/.bashrc
configs deps            # source tree for the current shell
configs open ~/.bashrc  # open with your editor

tmenu                   # roomy session picker with window preview
tn project              # new session; switches safely inside tmux
ta project              # attach, or switch if already inside
td                      # detach without stopping work
```

`aliases` inspects the current shell, including sourced definitions, rather
than guessing which dotfiles are active. It does not evaluate file contents.
Do not share its output without checking for sensitive values in your own
aliases. The search helpers treat their terms literally; raw `rg` remains
available for regular expressions. `sfind` uses ripgrep and its normal ignore
rules when available; its standard grep fallback searches hidden and ignored
files too, so start from a specific directory; `dfind` traverses directories except `.git` and does not follow symlinks.

`configs` is part of Helpers in both modes. Reload your shell after installation
so its wrapper can identify the calling Bash/Zsh, login status and `ZDOTDIR`.
Without the wrapper it uses `$SHELL` and assumes an interactive non-login shell.
Paths are terminal hyperlinks when output goes to a terminal, and plain paths
when piped. Your terminal handles `file://` links; on SSH it may need remote-file
support. `configs open FILE` uses `$VISUAL`/`$EDITOR` (an executable path or command
with simple space-separated arguments), then macOS `open -t` or Linux `xdg-open`.
The latter uses your desktop file association, which you can set to a text editor.

Plain `configs` lists existing candidates once and summarizes missing paths,
unresolved sources and incomplete scans. These are not startup error reports:
references inside uncalled functions and unmet conditions are candidates too.

In `configs deps`, each indented child is a possible file sourced by its parent; line numbers point
to the source statement. The scanner follows `.` and `source`, quoted paths,
exported variables, simple assignments within a file, and `${VAR:-fallback}`.
It never runs config code. Conditions, functions, shell options, runtime changes
to directories/variables and computed paths prevent a static scan from proving
exactly what was loaded. Dynamic sources are marked unresolved; complex heredocs
or multiline quotes stop that file's scan with a separate “scan stopped” marker. Variables assigned
by one file are not propagated into another. This is a startup/source map, not
an execution trace or a scan of every application's settings.

`-f` chooses one root; `-d DIRECTORY` requires an existing directory and visits regular files recursively (except `.git`
and symlinks). Together, `-d` resolves a relative `-f`. Relative source paths use
the invocation working directory and shell search order, not the config's parent
directory. Source cycles and repeated files are marked; recursion stops at 32
levels. Keep directory scans focused on your shell config directory.

The `legacy/` directory preserves reviewed, portable existing Python utilities
and their tests. Machine-specific fleet wrappers and whole dotfiles stay on
the original machine; their defaults don't belong in a portable toolkit.

## Edit and extend

```sh
cheat edit tmux          # edit the source with $EDITOR
cheat list              # list all sheets
```

Add `sheets/NAME.md` to get `cheat NAME`; no registry or build step is needed.
Keep lines at most 80 characters, put daily shortcuts first, group arrow
navigation on one line, and link to official documentation for deeper topics.
F1–F4 are the initial bindings; new sheets don't consume keys automatically.

The `tmux-reference` skill is linked into standard Codex, Claude, shared agents,
Gemini and Antigravity discovery directories by the installer. Other harnesses
can link `skills/tmux-reference` into their SKILL.md discovery location. Restart
or refresh the harness's skill discovery after installation.

Sheila shows today's tip at the top of the tmux reference. It comes directly
from the sheet's compact shortcuts, so edits stay in sync. `cheat tip` prints
it on demand; `CHEAT_TIPS=0` disables the inserted tip. Tips never intercept
keyboard input or create an extra pane. Phone profiles don't auto-open help.

## Verify

One command runs every check this machine can support:

```sh
python3 -B tests/run_all.py
```

Python is the test harness only, never part of installation. A missing optional
dependency is reported as a skip with its reason, not a failure, so the same
command is correct on a machine without tmux, fzf or the Rich environment.

| Tier | Additionally needs | Suites |
|---|---|---|
| Installer and scanner | Bash, standard Unix tools | `install_check`, `install_keys`, `configs_check`, `legacy` |
| Vanilla integration | tmux >= 3.2, less, an editor | `pty_check:vanilla`, `shell_keys:vanilla` |
| Enhanced | fzf, the private Rich environment | `render_check`, `check`, `pty_check:enhanced`, `shell_keys:enhanced` |

Name fragments select a subset, and a wedged PTY suite is capped rather than
left to hang:

```sh
python3 -B tests/run_all.py configs render
SHELL_KIT_TEST_TIMEOUT=120 python3 -B tests/run_all.py
```

Every suite remains a standalone script, for example `python3 -B tests/check.py`
or `python3 -B tests/pty_check.py vanilla`.

Checks use a temporary HOME and isolated tmux socket, never the live server.
Use `SHELL_KIT_TEST_BASH=/path/to/bash` for installer/selector checks, and put
that Bash binary first in PATH to exercise its function-key bindings.
On Bash 3.2, F1-F4 use internal Ctrl-X1 through Ctrl-X4 Readline macros to avoid
that version's limit on long `bind -x` key sequences.
Reference sources: [tmux manual](https://man.openbsd.org/tmux.1),
[Vim help](https://vimhelp.org/), and
[ripgrep guide](https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md).

Regular Vim was also checked on Linux by downloading matching `vim`,
`vim-runtime` and `vim-common` packages and extracting them with `dpkg-deb -x`
into a temporary prefix, without a system install. Point `VIMRUNTIME` at that
prefix's `usr/share/vim/vim91` and place a wrapper for `usr/bin/vim.basic` first
in `PATH` to run the editor/PTY checks against full Vim instead of a `vim` alias
that launches Neovim. Use the runtime directory matching your downloaded version.
