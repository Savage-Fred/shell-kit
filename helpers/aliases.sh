#!/usr/bin/env bash
# shellcheck shell=bash
case $- in *i*) ;; *) return 0 2>/dev/null || exit 0 ;; esac
# Directory aliases with eza / ls fallbacks.

if command -v eza >/dev/null 2>&1; then
    alias ls='eza'
    alias ll='eza -la'
    alias l='eza -l'
    alias la='eza -a'
    alias lt='eza --tree'
else
    if ls --color=auto -d . >/dev/null 2>&1; then
        alias ls='ls --color=auto'
    elif ls -G -d . >/dev/null 2>&1; then
        alias ls='ls -G'
    else
        alias ls='ls'
    fi
    alias ll='ls -la'
    alias l='ls -l'
    alias la='ls -a'
fi
