#!/usr/bin/env bash
# shellcheck shell=bash
case $- in *i*) ;; *) return 0 2>/dev/null || exit 0 ;; esac
# Prompt initialization with starship guard and standard fallback. An existing
# prompt wins: the fallback only replaces an empty PS1 or the shell's built-in
# default, and starship is not initialised a second time.

function _sk_setup_prompt {
    if command -v starship >/dev/null 2>&1; then
        [ -z "${STARSHIP_SHELL-}" ] || return 0
        if [ -n "${BASH_VERSION-}" ]; then
            eval "$(starship init bash)"
        elif [ -n "${ZSH_VERSION-}" ]; then
            eval "$(starship init zsh)"
        fi
        return 0
    fi
    # Built-in defaults: Bash '\s-\v\$ ', Zsh '%m%# '.
    case ${PS1-} in ''|'\s-\v\$ '|'%m%# ') ;; *) return 0 ;; esac
    if [ -n "${BASH_VERSION-}" ]; then
        export PS1='[\u@\h \W]\$ '
    elif [ -n "${ZSH_VERSION-}" ]; then
        export PS1='%n@%m %1~ %# '
    fi
}
_sk_setup_prompt
unset -f _sk_setup_prompt
