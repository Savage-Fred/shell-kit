#!/usr/bin/env bash
# shellcheck shell=bash
case $- in *i*) ;; *) return 0 2>/dev/null || exit 0 ;; esac
# Directory aliases with eza / ls fallbacks. Existing aliases and functions win:
# a name the user already defined is left alone.

function _sk_alias {
    alias "$1" >/dev/null 2>&1 && return 0
    typeset -f "$1" >/dev/null 2>&1 && return 0
    alias "$1=$2"
}

if command -v eza >/dev/null 2>&1; then
    _sk_alias ls 'eza'
    _sk_alias ll 'eza -la'
    _sk_alias l 'eza -l'
    _sk_alias la 'eza -a'
    _sk_alias lt 'eza --tree'
else
    if command ls --color=auto -d . >/dev/null 2>&1; then
        _sk_alias ls 'ls --color=auto'
    elif command ls -G -d . >/dev/null 2>&1; then
        _sk_alias ls 'ls -G'
    fi
    _sk_alias ll 'ls -la'
    _sk_alias l 'ls -l'
    _sk_alias la 'ls -a'
fi
unset -f _sk_alias
