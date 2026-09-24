# Source from interactive Bash or Zsh. Existing user definitions win.
# shellcheck shell=bash
case $- in *i*) ;; *) return ;; esac
export SHELL_KIT_ROOT="$HOME/.local/share/shell-kit"
case ":$PATH:" in *":$HOME/.local/share/shell-kit-runtime/bin:"*) ;; *) export PATH="$HOME/.local/share/shell-kit-runtime/bin:$PATH" ;; esac
if [ ! -f "$HOME/.local/state/shell-kit/install.tsv" ]; then
    # Keep an existing installation usable until the owner runs the new manager.
    case ":$PATH:" in *":$SHELL_KIT_ROOT/bin:"*) ;; *) export PATH="$SHELL_KIT_ROOT/bin:$PATH" ;; esac
fi
case "${SHELL_KIT_COMPONENTS- helpers references tmux }" in *' helpers '*)

if ! type aliases >/dev/null 2>&1; then
    function aliases {
        { alias; typeset -f; } | command shell-kit-search aliases "${1-}"
    }
fi
if ! typeset -f configs >/dev/null 2>&1 && ! alias configs >/dev/null 2>&1; then
    function configs {
        local _sk_login=0 _sk_shell _sk_binary
        if [ -n "${BASH_VERSION-}" ]; then
            _sk_shell=bash; _sk_binary=$BASH
            shopt -q login_shell && _sk_login=1
        else
            _sk_shell=zsh; _sk_binary=$(command -v zsh) || _sk_binary=zsh
            [[ -o login ]] && _sk_login=1
        fi
        CONFIGS_SHELL=$_sk_shell CONFIGS_BINARY=$_sk_binary CONFIGS_LOGIN=$_sk_login \
            CONFIGS_ZDOTDIR=${ZDOTDIR:-$HOME} command configs "$@"
    }
fi
if ! type sfind >/dev/null 2>&1; then
    function sfind { command shell-kit-search sfind "$@"; }
fi
if ! type dfind >/dev/null 2>&1; then
    function dfind { command shell-kit-search dfind "$@"; }
fi
if ! type pfind >/dev/null 2>&1; then
    function pfind { command shell-kit-search pfind "$@"; }
fi
;; esac
case "${SHELL_KIT_COMPONENTS- helpers references tmux }" in *' tmux '*)
if ! type tn >/dev/null 2>&1; then
    function tn {
        # tsessions starts the server in its own systemd scope, so the sessions
        # survive the terminal being closed or reclaimed under memory pressure.
        if command -v tsessions >/dev/null 2>&1; then command tsessions new "$@"
        elif [ -n "${TMUX-}" ]; then
            command tmux new-session -d -s "${1:?usage: tn NAME}" && command tmux switch-client -t "$1"
        else command tmux new-session -s "${1:?usage: tn NAME}"; fi
    }
fi
if ! type tk >/dev/null 2>&1; then
    function tk { command tsessions kill "${1:?usage: tk PATTERN | SESSION:WINDOW}"; }
fi
if ! type tfreeze >/dev/null 2>&1; then
    function tfreeze { command tsessions freeze "${1:?usage: tfreeze PATTERN}"; }
fi
if ! type tthaw >/dev/null 2>&1; then
    function tthaw { command tsessions thaw "${1:?usage: tthaw PATTERN}"; }
fi
if ! type tl >/dev/null 2>&1; then
    function tl {
        if command -v tsessions >/dev/null 2>&1; then command tsessions list "$@"
        elif [ "$#" -gt 0 ]; then
            printf 'tl: searching needs tsessions; re-run shell-kit install.sh\n' >&2
            return 1
        else command tmux list-sessions; fi
    }
fi
if ! type ta >/dev/null 2>&1; then
    function ta {
        # No argument reattaches the most recent session; a pattern matches the
        # session name, the command running in it, or its working directory.
        if command -v tsessions >/dev/null 2>&1; then command tsessions attach "$@"
        elif [ -n "${TMUX-}" ]; then command tmux switch-client -t "${1:?usage: ta NAME}"
        else command tmux attach-session -t "${1:?usage: ta NAME}"; fi
    }
fi
if ! type td >/dev/null 2>&1; then
    function td { command tmux detach-client; }
fi
;; esac
case "${SHELL_KIT_COMPONENTS- helpers references tmux }" in *' references '*)
function _sk_tmux { command cheat tmux; }
function _sk_vim { command cheat vim; }
function _sk_grep { command cheat grep; }
function _sk_aliases { command cheat aliases; }
function _sk_git { command cheat git; }
function _sk_agents { command cheat agents; }
if [ -n "${BASH_VERSION-}" ]; then
  if [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
    # Bash 3.2 bind -x cannot execute the longer terminal F-key sequences.
    bind -x '"\C-x1":_sk_tmux'
    bind -x '"\C-x2":_sk_vim'
    bind -x '"\C-x3":_sk_grep'
    bind -x '"\C-x4":_sk_aliases'
    bind -x '"\C-x5":_sk_git'
    bind -x '"\C-x6":_sk_agents'
    bind '"\eOP":"\C-x1"'
    bind '"\eOQ":"\C-x2"'
    bind '"\eOR":"\C-x3"'
    bind '"\eOS":"\C-x4"'
    bind '"\e[11~":"\C-x1"'
    bind '"\e[12~":"\C-x2"'
    bind '"\e[13~":"\C-x3"'
    bind '"\e[14~":"\C-x4"'
    bind '"\e[15~":"\C-x5"'
    bind '"\e[17~":"\C-x6"'
  else
    bind -x '"\eOP":_sk_tmux'
    bind -x '"\eOQ":_sk_vim'
    bind -x '"\eOR":_sk_grep'
    bind -x '"\eOS":_sk_aliases'
    bind -x '"\e[11~":_sk_tmux'
    bind -x '"\e[12~":_sk_vim'
    bind -x '"\e[13~":_sk_grep'
    bind -x '"\e[14~":_sk_aliases'
    bind -x '"\e[15~":_sk_git'
    bind -x '"\e[17~":_sk_agents'
  fi
else
    zle -N _sk_tmux
    zle -N _sk_vim
    zle -N _sk_grep
    zle -N _sk_aliases
    zle -N _sk_git
    zle -N _sk_agents
    for _sk_map in emacs viins vicmd; do
        bindkey -M "$_sk_map" '\eOP' _sk_tmux
        bindkey -M "$_sk_map" '\eOQ' _sk_vim
        bindkey -M "$_sk_map" '\eOR' _sk_grep
        bindkey -M "$_sk_map" '\eOS' _sk_aliases
        bindkey -M "$_sk_map" '\e[11~' _sk_tmux
        bindkey -M "$_sk_map" '\e[12~' _sk_vim
        bindkey -M "$_sk_map" '\e[13~' _sk_grep
        bindkey -M "$_sk_map" '\e[14~' _sk_aliases
        bindkey -M "$_sk_map" '\e[15~' _sk_git
        bindkey -M "$_sk_map" '\e[17~' _sk_agents
    done
    unset _sk_map
fi
command cheat register
;; esac
