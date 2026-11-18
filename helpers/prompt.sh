#!/usr/bin/env bash
# shellcheck shell=bash
case $- in *i*) ;; *) return 0 2>/dev/null || exit 0 ;; esac
# Prompt initialization with starship guard and standard fallback. An installed
# starship is started once per shell. Without it an existing prompt wins: the
# fallback only replaces an empty PS1 or the shell's built-in default, and is
# not exported, so a child shell of the other kind never inherits it.

function _sk_setup_prompt {
    if command -v starship >/dev/null 2>&1; then
        # Starship's own hook functions exist only in a shell it has set up.
        # STARSHIP_SHELL is exported, so child shells inherit it uninitialised.
        typeset -f starship_precmd >/dev/null 2>&1 && return 0
        typeset -f prompt_starship_precmd >/dev/null 2>&1 && return 0
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
        PS1='[\u@\h \W]\$ '
    elif [ -n "${ZSH_VERSION-}" ]; then
        PS1='%n@%m %1~ %# '
    fi
}
_sk_setup_prompt
unset -f _sk_setup_prompt
