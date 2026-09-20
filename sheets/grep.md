# Search · useful answers quickly

**F3** toggle this sheet · F1 tmux · F2 vim · F4 aliases · F5 git\
Quote search text. Helpers below treat it as literal text, not regex.

## Reach first

```sh
sfind 'timeout' .       # full paths + matching line and 1 above/below
dfind 'config' .        # directories with partial name; full paths
pfind 'ERROR' app.log   # each match through next blank line
aliases grep           # find search-related aliases and functions
```

Omit the directory to search here. `sfind` uses ripgrep's usual ignore
rules; `dfind` searches directory names. `pfind` is for text files.

## ripgrep · choose the answer shape

```sh
rg -n -C 1 -F -- 'needle' .    # numbered lines, literal, +/-1 context
rg -l -F -- 'needle' "$PWD"    # full paths of matching files only
rg -L -F -- 'needle' .         # follow symlinks (NOT files without match)
rg --files-without-match -F -- 'needle' .
rg --files -g '*.py'           # list Python paths, no content search
rg -n -i -- 'timeout' .        # ignore case
rg -n -w -- 'port' .           # whole word
rg -n -g '*.py' -- 'TODO' .    # restrict file glob
rg -n -g '!vendor/**' -- 'TODO' .
rg -n --hidden -g '!.git/**' -- 'TODO' .
```

`rg` normally skips hidden, ignored and binary files.\
`--hidden` includes hidden files; `--no-ignore` includes ignored files.\
`--` ends options: search safely for text such as `'-n'`.

## Regex, when useful

```sh
rg -n -- 'error|warning' .     # either alternative
rg -n -- '^def ' .            # line begins with def
rg -n -- ':[0-9]+$' .         # colon + digits at line end
rg -n -e 'error' -e 'warning' .
```

`-F` disables regex: use it for dots, brackets and user-provided text.

## Keep color while paging

```sh
rg --color=always -n -C 1 -- 'pattern' . | less -R
```

In less: `/text` search · `n/N` next/previous · `g/G` top/bottom · `q` quit.

[Official ripgrep guide][rg-guide]

[rg-guide]: https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md

## grep on machines without ripgrep

```sh
grep -n -F -C 1 -- 'needle' file.txt
grep -r -l -F -- 'needle' "$PWD"
```

Use `rg -l -0` with `xargs -0` if piping filenames to another command;
filenames can contain spaces and newlines. Preview matches before edits.
