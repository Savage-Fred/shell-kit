" Sheila's read-only references. Vim and Neovim; no plugin dependency.
if exists('g:loaded_shell_kit') | finish | endif
let g:loaded_shell_kit = 1
let s:root = expand('~/.local/share/shell-kit')
let s:owner = 'vim-' . getpid()

function! ShellKitSheet(topic, auto) abort
  if a:auto && ((empty($TMUX) && &columns < 120) || index(['desktop', 'macbook'], trim(system(shellescape(s:root . '/bin/cheat') . ' profile'))) < 0)
    return
  endif
  if !empty($TMUX)
    let cmd = shellescape(s:root . '/bin/cheat') . ' ' . (a:auto ? 'auto ' : '') . a:topic . ' ' . shellescape($TMUX_PANE) . ' ' . shellescape(s:owner)
    call system(cmd)
    return
  endif
  let home = win_getid()
  let sheets = filter(getwininfo(), 'v:val.tabnr == tabpagenr() && getwinvar(v:val.winid, "shell_kit", "") != ""')
  for win in sheets
    if getwinvar(win.winid, 'shell_kit') == a:topic
      if !a:auto | call win_execute(win.winid, 'close') | endif
      return
    endif
  endfor
  if &columns < 120
    " Manual help in its own tab leaves the edited file untouched.
    tabnew
  elseif empty(sheets)
    execute 'topleft ' . min([80, &columns * 2 / 5]) . 'vnew'
  else
    call win_gotoid(sheets[0].winid)
    belowright new
  endif
  execute 'silent read ' . fnameescape(s:root . '/sheets/' . a:topic . '.md')
  silent 1delete _
  let w:shell_kit = a:topic
  setlocal buftype=nofile bufhidden=wipe noswapfile nobuflisted
  if !exists('g:syntax_on') | syntax enable | endif
  if !exists('g:markdown_fenced_languages') | let g:markdown_fenced_languages = ['sh', 'python', 'vim'] | endif
  setlocal filetype=markdown nonumber norelativenumber wrap linebreak
  setlocal readonly nomodifiable winfixwidth
  nnoremap <buffer> q :close<CR>
  normal! gg
  if &columns >= 120 | call win_gotoid(home) | endif
endfunction

function! ShellKitCleanup() abort
  " Quitting the last work window must not leave Vim stranded in help.
  let wins = filter(getwininfo(), 'v:val.tabnr == tabpagenr()')
  let work = filter(copy(wins), 'getwinvar(v:val.winid, "shell_kit", "") == ""')
  if len(work) == 1 && work[0].winid == win_getid()
    for win in wins
      if getwinvar(win.winid, 'shell_kit', '') != ''
        call win_execute(win.winid, 'close')
      endif
    endfor
  endif
endfunction

for [s:key, s:topic] in [['F1','tmux'], ['F2','vim'], ['F3','grep'], ['F4','aliases']]
  execute 'nnoremap <silent> <' . s:key . '> :call ShellKitSheet("' . s:topic . '", 0)<CR>'
  execute 'inoremap <silent> <' . s:key . '> <C-O>:call ShellKitSheet("' . s:topic . '", 0)<CR>'
  execute 'xnoremap <silent> <' . s:key . '> :<C-U>call ShellKitSheet("' . s:topic . '", 0)<CR>gv'
endfor
augroup ShellKit
  autocmd!
  autocmd VimEnter * call ShellKitSheet('vim', 1)
  autocmd QuitPre * call ShellKitCleanup()
  autocmd VimLeavePre * if !empty($TMUX) | call system(shellescape(s:root . '/bin/cheat') . ' close-owner ' . shellescape(s:owner)) | endif
augroup END
