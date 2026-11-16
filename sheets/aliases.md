# Aliases & functions · discover what you already have

**F4** toggle this sheet · F1 tmux · F2 vim · F3 grep · F5 git\
F6 agents

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
tl               # list/search tmux sessions by name, command, path
tn work          # create named tmux session
ta work          # attach/switch by name or pattern (no argument: most recent)
ta work:2        # exact session, that window
td               # detach current tmux client
tk work          # kill a session, or tk work:2 for one window
tfreeze work     # suspend the work running in a session
tthaw work       # resume it
```

## PGP with named identities

```sh
pgp ids               # your keys: name, fingerprint, expiry, trust (* = active)
pgp use anon          # sign/encrypt as anon in this shell; pgp use - clears
pgp sign msg.txt      # clearsign as the active identity (-u ID overrides)
pgp encrypt -r bob f  # to bob + yourself; no -r: just yourself; -k: paste key
pgp decrypt f.asc     # or paste; pgp verify [FILE | SIG DATA]
pgp doctor            # agent, ownertrust, expiry, pass recipients
```

Name keys once: `PGP_IDENTITIES='me=FPR anon=FPR'`, `PGP_IDENTITY=me`.
"Unusable public key" on your own key (and failing `pass insert`) means its
ownertrust slipped below ultimate: `pgp trust ID`.

## Alias or function?

An alias abbreviates a command. A function can use arguments explicitly.
Keep personal definitions in a sourced file; reuse helpers from the repo.

```sh
alias gs='git status --short'
croot() { cd "$(git rev-parse --show-toplevel)"; }
```

Quote `"$@"` when forwarding all arguments. Try new definitions in a shell
before saving them. Open a fresh shell after updating startup files.
