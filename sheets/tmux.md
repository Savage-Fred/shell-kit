# tmux · stay oriented

**F1** toggle this sheet · F2 vim · F3 grep · F4 aliases · F5 git\
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
tmenu          # roomy session chooser
tn research    # create named session
ta research    # attach / switch
td             # detach
```

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
