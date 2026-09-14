# Vim · move, select, edit

**F2** toggle this sheet · F1 tmux · F3 grep · F4 aliases\
**Esc** returns to Normal mode. `Ctrl-x` means hold Ctrl and press x.

## Reach first · Normal mode

`h j k l` left / down / up / right\
`w` next word · `b` previous word · `e` end of word\
`0` line start · `^` first text · `$` line end\
`gg` file start · `G` file end · `42G` line 42\
`Ctrl-d` half page down · `Ctrl-u` half page up\
`zz` center cursor · `zt` cursor to top · `zb` cursor to bottom\
`/text` search forward · `?text` search back\
`n` next match · `N` previous match · `*` search cursor word

## Start typing · Insert mode

`i` insert before cursor · `a` insert after cursor\
`I` insert at first text · `A` append at end of line\
`o` open line below · `O` open line above\
`u` undo · `Ctrl-r` redo · `.` repeat last change

## Select · Visual mode

`v` select characters\
`V` select whole lines\
`Ctrl-v` select a rectangular block\
`o` switch the active end of the selection\
`gv` restore your last selection · `Esc` cancel

Move with any Normal-mode motion to extend the selection.

## Select a text object

`viw` inside word · `vaw` word plus its space\
`vi"` inside quotes · `va"` quotes included\
`vi(` inside parentheses · `va(` parentheses included\
`vi{` inside braces · `vit` inside an HTML/XML tag\
`vip` inside paragraph · `vap` paragraph plus blank line

`i` means inside, `a` means around (delimiters included).

## Act on a selection

`y` copy · `d` cut · `c` replace and start typing\
`>` indent · `<` unindent · `=` autoindent\
`~` swap case · `u` lowercase · `U` uppercase\
`J` join the selected lines

## Edit a column · Visual block

`Ctrl-v`, select rows, `I`, type, then **Esc** inserts on every row.\
`Ctrl-v`, select rows, `A`, type, then **Esc** appends on every row.\
`Ctrl-v`, select rows, `$`, `A` appends at each ragged line end.\
Inspect short lines afterward; blocks skip lines that end early.

[Visual mode guide](https://vimhelp.org/visual.txt.html)

## Compose edits · Normal mode

`d` delete · `c` change · `y` copy; each takes a motion or object.\
`dw` delete word · `3dw` delete three words · `d$` delete to line end\
`dd` cut line · `yy` copy line · `cc` replace line\
`ci"` replace quoted text · `da(` delete including parentheses\
`p` put after cursor · `P` put before cursor\
`x` delete character · `r` replace one character

## Registers and clipboard

`"ayiw` yank word into register a · `"ap` put register a\
`:registers` inspect what is stored\
`"+y` copy to the OS clipboard, if Vim has clipboard support\
`"+p` put from the OS clipboard

## Find on a line · jump back

`fX` jump to next X · `tX` stop before X\
`FX` jump back to X · `;` repeat find · `,` reverse find\
`%` matching bracket\
`Ctrl-o` older position · `Ctrl-i` newer position\
`` `` `` back to the last jump

[Quick reference](https://vimhelp.org/quickref.txt.html)

## Search, replace, repeat

```vim
:%s/old/new/gc     " whole file, each match, confirm
:'<,'>s/old/new/g  " selected lines; : fills in the range
:nohlsearch        " clear search highlights
```

Record: `qa`, make edits, `q`. Replay: `@a`; repeat last macro: `@@`.

## Split the window · layout

`:vs file` split left/right · `Ctrl-w v` split current file left/right\
`:sp file` split top/bottom · `Ctrl-w s` split current file top/bottom\
`Ctrl-w =` equalize every split\
`Ctrl-w _` maximize height · `Ctrl-w |` maximize width\
`Ctrl-w 20+` grow 20 rows · `Ctrl-w 20>` widen 20 columns\
`Ctrl-w o` close every split but this one · `Ctrl-w c` close this one\
`Ctrl-w H/J/K/L` move this split to the far left/bottom/top/right\
`Ctrl-w T` move this split into its own tab

## Move focus between splits

`Ctrl-w h` focus the split to the left\
`Ctrl-w j` focus the split below\
`Ctrl-w k` focus the split above\
`Ctrl-w l` focus the split to the right\
`Ctrl-w w` cycle forward · `Ctrl-w p` previous split

Press `Ctrl-w`, release, then the direction key.

## Move between this sheet and your file

**Inside tmux**, the sheet is a pane beside Vim, not a Vim split:\
`Prefix ←` focus the sheet · `Prefix →` focus your editor\
`Prefix ↑` / `Prefix ↓` move between stacked sheets\
`Prefix o` cycle panes · `Prefix z` zoom the focused pane\
`F2` closes the sheet from either pane · `q` closes it from inside\
Prefix is `Ctrl-b` unless you changed it; see the tmux sheet (F1).\
In a narrow window the sheet opens as its own tmux window instead:\
`Prefix n` / `Prefix p` next / previous window · `Prefix w` pick one

**Without tmux**, the sheet is a Vim split on the left:\
`Ctrl-w l` back to your file · `Ctrl-w h` back to the sheet\
`q` inside the sheet closes it · `F2` toggles it\
Below 120 columns the sheet opens in its own tab instead:\
`gt` next tab · `gT` previous tab · `1gt` first tab

The sheet is read-only, so edits land in your file, never here.

## Tabs and buffers

`:tabnew file` new tab · `gt` / `gT` next / previous tab\
`:tabclose` close tab · `:tabonly` keep only this tab\
`:ls` list buffers · `:b 2` go to buffer 2 · `:bn` / `:bp` next / previous\
`Ctrl-^` alternate buffer

## Save and quit

`:w` save · `:w file` save as\
`:q` quit · `:wq` save and quit · `:q!` discard changes\
`:qa` quit every window · `:wqa` save all and quit

## Make settings stick

Edit `~/.vimrc`; try each setting first with `:` in Vim.

```vim
set number
set relativenumber
set incsearch hlsearch
set ignorecase smartcase
set scrolloff=4
set splitright splitbelow
nnoremap <leader>h :nohlsearch<CR>
```

Default leader is backslash. `:source ~/.vimrc` reloads.\
`:verbose set number?` shows where a setting came from.\
`:verbose map <F2>` inspects a conflicting shortcut.\
`:help topic` opens local help; `Ctrl-]` follows a help tag.\
[Customization](https://vimhelp.org/usr_40.txt.html)
