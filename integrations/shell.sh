# Source from interactive Bash or Zsh. Existing user definitions win.
case $- in *i*) ;; *) return ;; esac
export SHELL_KIT_ROOT="$HOME/.local/share/shell-kit"
case ":$PATH:" in *":$SHELL_KIT_ROOT/bin:"*) ;; *) export PATH="$SHELL_KIT_ROOT/bin:$HOME/.local/share/shell-kit-runtime/bin:$PATH" ;; esac

if ! type aliases >/dev/null 2>&1; then
    aliases() {
        { alias; typeset -f; } | command shell-kit-search aliases "${1-}"
    }
fi
if ! type sfind >/dev/null 2>&1; then
    sfind() { command shell-kit-search sfind "$@"; }
fi
if ! type dfind >/dev/null 2>&1; then
    dfind() { command shell-kit-search dfind "$@"; }
fi
if ! type pfind >/dev/null 2>&1; then
    pfind() { command shell-kit-search pfind "$@"; }
fi
if ! type tn >/dev/null 2>&1; then
    tn() {
        if [ -n "${TMUX-}" ]; then
            command tmux new-session -d -s "${1:?usage: tn NAME}" && command tmux switch-client -t "$1"
        else command tmux new-session -s "${1:?usage: tn NAME}"; fi
    }
fi
if ! type ta >/dev/null 2>&1; then
    ta() {
        if [ -n "${TMUX-}" ]; then command tmux switch-client -t "${1:?usage: ta NAME}"
        else command tmux attach-session -t "${1:?usage: ta NAME}"; fi
    }
fi
if ! type td >/dev/null 2>&1; then
    td() { command tmux detach-client; }
fi
_sk_tmux() { command cheat tmux; }
_sk_vim() { command cheat vim; }
_sk_grep() { command cheat grep; }
_sk_aliases() { command cheat aliases; }
if [ -n "${BASH_VERSION-}" ]; then
    bind -x '"\eOP":_sk_tmux'
    bind -x '"\eOQ":_sk_vim'
    bind -x '"\eOR":_sk_grep'
    bind -x '"\eOS":_sk_aliases'
    bind -x '"\e[11~":_sk_tmux'
    bind -x '"\e[12~":_sk_vim'
    bind -x '"\e[13~":_sk_grep'
    bind -x '"\e[14~":_sk_aliases'
else
    zle -N _sk_tmux
    zle -N _sk_vim
    zle -N _sk_grep
    zle -N _sk_aliases
    for _sk_map in emacs viins vicmd; do
        bindkey -M "$_sk_map" '\eOP' _sk_tmux
        bindkey -M "$_sk_map" '\eOQ' _sk_vim
        bindkey -M "$_sk_map" '\eOR' _sk_grep
        bindkey -M "$_sk_map" '\eOS' _sk_aliases
        bindkey -M "$_sk_map" '\e[11~' _sk_tmux
        bindkey -M "$_sk_map" '\e[12~' _sk_vim
        bindkey -M "$_sk_map" '\e[13~' _sk_grep
        bindkey -M "$_sk_map" '\e[14~' _sk_aliases
    done
    unset _sk_map
fi
command cheat register
