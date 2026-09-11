---
name: tmux-reference
description: Help use tmux or maintain Sheila shell-kit cheat sheets and sidebar behavior. Use for tmux navigation, session help, reference updates, or broken cheat-sheet startup and toggles.
---

# Sheila's terminal references

Find the installed repo via `~/.local/share/shell-kit` (a symlink), then read
its README and relevant `sheets/*.md`. The same source supports Codex, Claude,
Antigravity and harnesses that discover standard SKILL.md directories.

For questions, give the shortest useful command and explain the prefix notation.
Check the user's actual tmux prefix and mode-keys before assuming defaults.
For a requested reference update, edit Markdown in the source repo; do not edit
rendered output or copy entire manuals. Keep lines <=80 characters and put
compact daily navigation first. End the tmux sheet with its three decision
bullets. New sheets need only a new Markdown file; keyboard bindings are optional.

For behavioral changes, trace `bin/cheat`, `integrations/tmux.conf`, the shell
bindings and Vim integration. Preserve these invariants:

- Automatic opening retains work focus and does not duplicate an existing sheet.
- Multiple tmux sheets stack in the left column, preserving work panes.
- A Vim exit closes only the sheet created automatically for that editor owner.
- Unknown remote clients and phone profiles do not automatically open help.
- Client addresses and machine settings belong in local config, never the repo.
- F1/F2/F3/F4 are consistent across shell, tmux and editor. Terminal apps must
  transmit them; a harness cannot override OS-reserved keys.

Run `python3 tests/check.py` in the repo and test pane changes on an isolated
`tmux -L` server. Never kill the user's server or rearrange unrelated work panes.
Use `python3 install.py --dry-run` before changing integration files; the installer
backs up edits and supports uninstall. Do not publish local aliases, credentials,
or entire dotfiles when adding reusable helpers.
