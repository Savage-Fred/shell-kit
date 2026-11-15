#!/usr/bin/env bash
# shellcheck shell=bash
case $- in *i*) ;; *) return 0 2>/dev/null || exit 0 ;; esac
# Shared shell helper functions with graceful degradation for optional dependencies.
# Supported fallbacks:
#   fif:    rg + fzf + bat/batcat -> grep -rn + less/cat
# sfind, dfind and pfind are not defined here: integrations/shell.sh maps them
# to vanilla/shell-kit-search, whose behaviour the README and sheets document.
# Existing definitions win: a name already taken by an alias, function or
# command is skipped. The `function NAME` form is deliberate; `NAME() {` would
# be rewritten by a same-named alias while the definition is parsed.
# Optional tools are resolved to a real executable when a helper runs, so the
# user's aliases and functions for rg, fzf, bat or less are neither frozen
# into these bodies nor mistaken for the binary.

# Print the path of the first NAME that is a real executable. An alias or
# function of that name does not count: `command -v` would report it instead
# of the binary behind it, and it cannot be run by path.
function _sk_bin {
    local name found
    for name in "$@"; do
        found=$(unalias -a 2>/dev/null; unset -f "$name" 2>/dev/null; command -v "$name" 2>/dev/null) || continue
        case $found in /*) printf '%s\n' "$found"; return 0 ;; esac
    done
    return 1
}

# fif: Find in files with graceful degradation.
# When rg, fzf, or bat/batcat is missing, cleanly falls back to grep -rn and standard pager.
if ! type fif >/dev/null 2>&1; then
function fif {
    local query="${1:-}"
    local target="${2:-.}"
    if [ -z "$query" ]; then
        printf 'Usage: fif PATTERN [DIR]\n' >&2
        return 0
    fi

    local rg_cmd fzf_cmd bat_cmd less_cmd
    rg_cmd=$(_sk_bin rg) || rg_cmd=""
    fzf_cmd=$(_sk_bin fzf) || fzf_cmd=""
    bat_cmd=$(_sk_bin bat batcat) || bat_cmd=""

    # The pager lives in "$@": Zsh does not split an unquoted $pager into words.
    if [ -t 1 ] && less_cmd=$(_sk_bin less); then
        set -- "$less_cmd" -R
    else
        set -- command cat
    fi

    # Interactive fuzzy search if fzf and a TTY are available
    if [ -t 0 ] && [ -t 1 ] && [ -n "$fzf_cmd" ]; then
        local preview_cmd
        if [ -n "$bat_cmd" ]; then
            preview_cmd="$bat_cmd --style=numbers --color=always --highlight-line {2} {1} 2>/dev/null || cat {1}"
        else
            preview_cmd="cat {1}"
        fi

        if [ -n "$rg_cmd" ]; then
            "$rg_cmd" --color=always --line-number --no-heading --smart-case -- "${query}" "${target}" 2>/dev/null | \
                "$fzf_cmd" --ansi \
                    --delimiter : \
                    --preview "$preview_cmd" \
                    --preview-window 'up,60%,border-bottom,+{2}+3/3,~3' || true
        else
            command grep -r -n -H -- "${query}" "${target}" 2>/dev/null | \
                "$fzf_cmd" --delimiter : \
                    --preview "$preview_cmd" \
                    --preview-window 'up,60%,border-bottom,+{2}+3/3,~3' || true
        fi
    else
        # Non-interactive or fzf missing: fall back to rg or grep -rn and standard pager
        if [ -n "$rg_cmd" ]; then
            "$rg_cmd" --line-number --color=auto -- "${query}" "${target}" 2>/dev/null | "$@" || true
        else
            command grep -r -n -H -- "${query}" "${target}" 2>/dev/null | "$@" || true
        fi
    fi
}
fi
