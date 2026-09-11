<img src="assets/sheila.svg" alt="Sheila the koala" width="120">

# Sheila's shell-kit

A saved home for small, reusable terminal tools. Sheila keeps the shortcuts
beside your work so you can stop looking them up.

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

In tmux, sheets stack on the **left**, work stays on the **right**, and opening
help keeps your typing focus. Move into help with `Ctrl-b ←`; use arrows,
PageUp/PageDown, `/` to search, `g` for the top, and `q` to close. The pager
starts at the top every time and highlights Markdown and fenced code with bat.
Links remain visible and can be opened using your terminal's link gesture.
The three-question tmux checklist is at the end of its sheet.

Standalone Vim/Neovim uses read-only Markdown splits with syntax highlighting,
keeps focus in the edited file, and closes its help when the last work window
quits. Vim inside tmux uses the shared left column. Its automatically opened
sheet closes when that Vim process exits; manually opened sheets stay open.
Closing the last work pane also removes the remaining help panes.

### Screen and client policy

| Situation | Automatic behavior | Manual help |
|---|---|---|
| Local desktop / Mac | tmux on attach, Vim on editor start | Left column |
| Known `macbook` remote profile | Same | Left column |
| `phone` or unidentified SSH client | Off | Available |
| Under 120 columns or 24 rows in tmux | Off | Temporary popup |
| Narrow standalone Vim | Off | Temporary help tab |
| Shell outside tmux | Off | Full-screen pager |

The column uses up to 80 characters, or 40% of window width. Multiple sheets
split the existing help column; work-pane splits stay intact. If another sheet
would be too short to read, manual help uses a popup instead.

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

Requires Python 3, tmux >=3.2, bat, less, ripgrep and fzf. Vim/Neovim integration
has no plugin dependency. Bash and Zsh are supported; POSIX vi without Vim
features is not.

```sh
# macOS
brew install tmux bat less ripgrep fzf python
# Debian / Ubuntu (bat's executable is often batcat)
sudo apt install tmux bat less ripgrep fzf python3

# Run in your checkout; its location and username do not matter.
python3 tests/check.py
python3 install.py --dry-run
python3 install.py
```

Open a **new shell**. For an existing tmux server, load the added bindings:

```sh
tmux source-file ~/.tmux.conf
```

The installer adds marked source blocks, keeps timestamped backups under
`~/.local/state/shell-kit/backups`, and is safe to rerun. It disables the old
`CheatsheetAuto` Vim autocmd group while leaving its definition in your vimrc.
It adds an init file for Neovim when one doesn't exist. Existing unrelated
aliases/functions win over helpers with the same name.

`python3 install.py --uninstall` removes only the managed source blocks and
matching links. Restart shells/editors and the tmux server when convenient to
clear already-loaded functions, hooks and bindings; do not kill a live server
with work you want to preserve. Original configuration backups remain available.

### Configure remote clients locally

No machine names, addresses, SSH keys or network assumptions are in this repo.
`~/.config/shell-kit/clients.json` is an initially empty, **untracked** mapping
from SSH source address to `macbook`, `desktop` or `phone`. You can add the
current client without hardcoding an address in any shared file:

```sh
# Run in an SSH shell connected from the client you want to recognize.
python3 - <<'PY'
import json, os
from pathlib import Path
path = Path.home() / '.config/shell-kit/clients.json'
data = json.loads(path.read_text())
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

tmenu                   # roomy session picker with window preview
tn project              # new session; switches safely inside tmux
ta project              # attach, or switch if already inside
td                      # detach without stopping work
```

`aliases` inspects the current shell, including sourced definitions, rather
than guessing which dotfiles are active. It does not evaluate file contents.
Do not share its output without checking for sensitive values in your own
aliases. The search helpers treat their terms literally; raw `rg` remains
available for regular expressions. `sfind` follows ripgrep's normal ignore
rules; `dfind` traverses directories except `.git` and does not follow symlinks.

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

The tmux tip of the day is deferred. The always-available reference comes first;
a short opt-in tip can be added without changing the layout or viewer.

## Verify

```sh
python3 tests/check.py
python3 tests/pty_check.py
python3 tests/shell_keys.py
python3 -m unittest discover -s legacy/homelab-shell/scripts -p 'test_*.py'
```

Checks use a temporary HOME and isolated tmux socket, never the live server.
Reference sources: [tmux manual](https://man.openbsd.org/tmux.1),
[Vim help](https://vimhelp.org/), and
[ripgrep guide](https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md).
