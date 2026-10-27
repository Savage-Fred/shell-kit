#!/usr/bin/env bash
# shellcheck shell=bash
case $- in *i*) ;; *) return 0 2>/dev/null || exit 0 ;; esac
# Prompt initialization with starship guard and standard fallback.

setup_prompt() {
    if command -v starship >/dev/null 2>&1; then
        if [ -n "${BASH_VERSION-}" ]; then
            eval "$(starship init bash)"
        elif [ -n "${ZSH_VERSION-}" ]; then
            eval "$(starship init zsh)"
        fi
    else
        # Clean standard prompt fallback
        if [ -n "${BASH_VERSION-}" ]; then
            export PS1='[\u@\h \W]\$ '
        elif [ -n "${ZSH_VERSION-}" ]; then
            export PS1='%n@%m %1~ %# '
        fi
    fi
}
setup_prompt
