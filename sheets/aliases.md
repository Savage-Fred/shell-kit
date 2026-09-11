# Aliases & functions · discover what you already have

**F4** toggle this sheet · F1 tmux · F2 vim · F3 grep

## Reach first

```sh
aliases          # discover loaded aliases and functions
aliases grep     # name or body contains grep
aliases l        # name starts with l
aliases ssh      # name or body contains ssh
```

One letter means name prefix; longer text means name/body substring.
This searches the running shell's definitions, including sourced files.
Inactive, conditional definitions are absent until their config is loaded.

## Identify what will run

```sh
type ssh         # alias, function, builtin, or executable?
type -a ssh      # every matching definition/path
alias ll         # inspect one alias
```

In Bash, inspect a function body with `declare -f NAME`.\
In Zsh, use `functions NAME`.

## Helpers in this collection

```sh
cheat tmux       # tmux reference
cheat vim        # Vim reference
cheat grep       # search reference
cheat aliases    # this reference
sfind 'text' .   # full paths and one line of surrounding context
dfind 'part' .   # directories by partial name
pfind 'text' log # match through the next blank line
tmenu            # readable tmux session chooser
tn work          # create named tmux session
ta work          # attach/switch to named session
td               # detach current tmux client
```

## Alias or function?

An alias abbreviates a command. A function can use arguments explicitly.
Keep personal definitions in a sourced file; reuse helpers from the repo.

```sh
alias gs='git status --short'
croot() { cd "$(git rev-parse --show-toplevel)"; }
```

Quote `"$@"` when forwarding all arguments. Try new definitions in a shell
before saving them. Open a fresh shell after updating startup files.
