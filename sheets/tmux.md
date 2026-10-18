# tmux · stay oriented

**F1** toggle this sheet · F2 vim · F3 grep · F4 aliases · F5 git\
F6 agents
**Prefix = Ctrl-b**, release, then press the next key.

## Reach first

`Prefix ← ↓ ↑ →` focus pane · `Prefix ;` previous pane\
`Prefix z` zoom/restore · `Prefix d` detach, keep work running\
`Prefix [` scroll/copy · `Prefix ]` paste tmux buffer\
`Prefix c` new window · `Prefix n/p` next/previous · `Prefix 0…9` jump\
`Prefix %` split left/right · `Prefix "` split top/bottom\
`Prefix ?` all bindings · `Prefix :` command prompt

## Copy and paste

Copy mode uses one of two key sets. Check yours in a shell:

```sh
tmux show-window-options -gv mode-keys
```

- **vi:** Space starts selection; Enter copies; q leaves.
- **emacs:** Ctrl-Space starts; Alt-w copies; Escape leaves.

Move with arrows; PageUp/PageDown scroll. tmux's buffer and your OS
clipboard are separate unless clipboard integration is available.

## Sessions, without memorizing the picker

```sh
tl             # list sessions: windows, idle time, command, path
tl studio      # search name, running command, or working directory
tmenu          # roomy session chooser
tn research    # create named session
ta research    # attach / switch by name or pattern
ta             # reattach the most recent session
td             # detach
tk work        # kill a session; tk work:2 kills one window
tfreeze work   # suspend the work running in it
tthaw work     # resume it
```

`tl` answers "which session was the build in?" when the names are `0`, `1`, `2`.
`ta` needs enough of a pattern to be unambiguous; it lists the rivals otherwise.

## Sessions that outlive the terminal

`tn` starts the tmux server inside its own systemd scope. A server started
straight from a terminal shares that terminal's cgroup, so closing the window,
or systemd-oomd reclaiming it under memory pressure, takes every session with
it. Only the server needs the scope: it forks every window and pane, so they
inherit it.

```sh
systemctl --user status shell-kit-tmux.scope   # where the sessions live
SHELL_KIT_TMUX_SCOPE=off tn work               # opt out for one session
```

Without systemd, as on macOS, this is a plain `tmux` call and nothing changes.

## Clearing out stale work

```sh
tl                 # what is idle, and what is running in it
tk old-branch      # kill that session
tk old-branch:3    # kill one window; a colon means an exact tmux target
tfreeze big-build  # SIGSTOP everything running in its panes
tthaw big-build    # SIGCONT the same processes
```

Freezing releases **CPU, not memory** — suspended processes keep their pages,
so kill a session to reclaim RAM. It reaches the work rather than the pane's
shell, because job control gives each job its own process group. A session
holding nothing but an idle shell reports that there was nothing to suspend.

## Reconnecting from another machine

Log in and use `tl` and `ta` normally, or go straight there in one command.
Startup files skip non-interactive shells, so name the command in full:

```sh
sk='$HOME/.local/share/shell-kit-runtime/bin/tsessions'
ssh HOST -t "$sk attach studio"   # land straight inside that session
ssh HOST -t "$sk attach"          # most recent session
ssh HOST "$sk list"               # just look, no terminal needed
```

`-t` is required to attach: tmux needs a terminal. Landing directly in a session
means no prefix key is needed to arrive, which matters on a phone keyboard.
Closing the client leaves the session running; only `td` or `Prefix d` detaches.

## Small improvements

`Prefix ,` rename window · `Prefix $` rename session\
`Prefix { / }` swap panes · `Prefix Space` cycle layouts\
`Prefix Ctrl-← ↓ ↑ →` resize · `Prefix !` pane to separate window

Reload edits to your configuration:

```sh
tmux source-file ~/.tmux.conf
```

`exit` closes a shell pane; detaching preserves it.\
[tmux manual](https://man.openbsd.org/tmux.1)

## Should I use tmux for this?

- Will the work need to survive an SSH disconnect?
- Do I need several shells visible together?
- Will I return to this named workspace later?
