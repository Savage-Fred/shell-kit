# Vim · move, select, edit

**F2** toggle this sheet · F1 tmux · F3 grep · F4 aliases
**Esc** returns to Normal mode. `Ctrl-x` means hold Ctrl and press x.

## Reach first · Normal mode

`h j k l` ← ↓ ↑ → · `w/b` word forward/back · `e` word end
`0 / ^ / $` line start / first text / end · `gg/G` file start/end
`Ctrl-d/u` half-page down/up · `zz` center cursor
`/text` search · `n/N` next/previous · `*` search cursor word
`i/a` insert before/after · `I/A` first text/end of line
`o/O` new line below/above · `u` undo · `Ctrl-r` redo · `.` repeat
`:w` save · `:q` quit · `:wq` save + quit · `:q!` discard changes

## Select well · Visual mode

`v` characters · `V` lines · `Ctrl-v` rectangular block
Move to extend selection; `o` switches the active end; `Esc` cancels.
`gv` restores your last selection.

`viw` word · `vi"` inside quotes · `vi(` parentheses · `vip` paragraph
Use `a` instead of `i` to include delimiters: `va"`, `va(`.

With a selection: `y` copy · `d` cut · `c` replace · `>` indent
`<` unindent · `=` autoindent · `~` swap case

Block insert: `Ctrl-v`, select rows, `I`, type, then **Esc**.
Block append: same sequence with `A`. Inspect short lines afterward.

[Visual mode guide](https://vimhelp.org/visual.txt.html)

## Compose edits · Normal mode

`d` delete · `c` change · `y` copy; add a motion or text object.
`ci"` replace quoted text · `da(` delete including parentheses
`3dw` delete three words · `dd/yy` cut/copy line · `p/P` put after/before
`"ayiw` word to register a · `"ap` paste a · `:registers` inspect
`"+y` copy selection to OS clipboard if Vim has clipboard support.

`fX/tX` find/stop before X · `; / ,` repeat/reverse that find
`%` matching bracket · `Ctrl-o/i` older/newer jump

[Quick reference](https://vimhelp.org/quickref.txt.html)

## Search, replace, repeat

```vim
:%s/old/new/gc     " whole file, each match, confirm
:'<,'>s/old/new/g  " selected lines; : fills in the range
:nohlsearch       " clear search highlights
```

Record: `qa`, make edits, `q`. Replay: `@a`; repeat last macro: `@@`.

## Windows and buffers

`:vs file` vertical split · `:sp file` horizontal split
`Ctrl-w h/j/k/l` focus split · `Ctrl-w =` equalize
`:ls` buffers · `:b 2` buffer 2 · `Ctrl-^` alternate buffer

## Make settings stick

Edit `~/.vimrc`; try each setting first with `:` in Vim.

```vim
set number
set relativenumber
set incsearch hlsearch
set ignorecase smartcase
set scrolloff=4
nnoremap <leader>h :nohlsearch<CR>
```

Default leader is backslash. `:source ~/.vimrc` reloads.
`:verbose set number?` shows where a setting came from.
`:verbose map <F2>` inspects a conflicting shortcut.
`:help topic` opens local help; `Ctrl-]` follows a help tag.
[Customization](https://vimhelp.org/usr_40.txt.html)
