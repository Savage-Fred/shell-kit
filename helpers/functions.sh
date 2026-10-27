#!/usr/bin/env bash
# shellcheck shell=bash
# Shared shell helper functions with graceful degradation for optional dependencies.
# Supported fallbacks:
#   fif:    rg + fzf + bat/batcat -> grep -rn + less/cat
#   sfind:  fd -> POSIX find (case-insensitive filename search)
#   dfind:  fd -> POSIX find (directory search)
#   pfind:  fd -> POSIX find (file path search)

# fif: Find in files with graceful degradation.
# When rg, fzf, or bat/batcat is missing, cleanly falls back to grep -rn and standard pager.
fif() {
    local query="${1:-}"
    local target="${2:-.}"
    if [ -z "$query" ]; then
        printf 'Usage: fif PATTERN [DIR]\n' >&2
        return 0
    fi

    local bat_cmd=""
    bat_cmd=$(command -v bat 2>/dev/null || command -v batcat 2>/dev/null || true)

    local pager="cat"
    if [ -t 1 ] && command -v less >/dev/null 2>&1; then
        pager="less -R"
    fi

    # Interactive fuzzy search if fzf and a TTY are available
    if [ -t 0 ] && [ -t 1 ] && command -v fzf >/dev/null 2>&1; then
        local preview_cmd
        if [ -n "$bat_cmd" ]; then
            preview_cmd="$bat_cmd --style=numbers --color=always --highlight-line {2} {1} 2>/dev/null || cat {1}"
        else
            preview_cmd="cat {1}"
        fi

        if command -v rg >/dev/null 2>&1; then
            rg --color=always --line-number --no-heading --smart-case -- "${query}" "${target}" 2>/dev/null | \
                fzf --ansi \
                    --delimiter : \
                    --preview "$preview_cmd" \
                    --preview-window 'up,60%,border-bottom,+{2}+3/3,~3' || true
        else
            grep -r -n -H -- "${query}" "${target}" 2>/dev/null | \
                fzf --delimiter : \
                    --preview "$preview_cmd" \
                    --preview-window 'up,60%,border-bottom,+{2}+3/3,~3' || true
        fi
    else
        # Non-interactive or fzf missing: fall back to rg or grep -rn and standard pager
        if command -v rg >/dev/null 2>&1; then
            rg --line-number --color=auto -- "${query}" "${target}" 2>/dev/null | $pager || true
        else
            grep -r -n -H -- "${query}" "${target}" 2>/dev/null | $pager || true
        fi
    fi
}

# sfind: Search files by pattern (using fd if available, falling back cleanly to POSIX find)
sfind() {
    local query="${1:-}"
    local target="${2:-.}"
    local fd_cmd=""
    fd_cmd=$(command -v fd 2>/dev/null || command -v fdfind 2>/dev/null || true)
    if [ -n "$fd_cmd" ]; then
        "$fd_cmd" --hidden --exclude .git -i "$query" "$target"
    else
        find "$target" -name .git -prune -o -iname "*$query*" -print
    fi
}

# dfind: Search directories by pattern (using fd if available, falling back cleanly to POSIX find)
dfind() {
    local query="${1:-}"
    local target="${2:-.}"
    local fd_cmd=""
    fd_cmd=$(command -v fd 2>/dev/null || command -v fdfind 2>/dev/null || true)
    if [ -n "$fd_cmd" ]; then
        "$fd_cmd" --type d --hidden --exclude .git -i "$query" "$target"
    else
        find "$target" -name .git -prune -o -type d -iname "*$query*" -print
    fi
}

# pfind: Search path/files (using fd if available, falling back cleanly to POSIX find)
pfind() {
    local query="${1:-}"
    local target="${2:-.}"
    local fd_cmd=""
    fd_cmd=$(command -v fd 2>/dev/null || command -v fdfind 2>/dev/null || true)
    if [ -n "$fd_cmd" ]; then
        "$fd_cmd" --type f --hidden --exclude .git -i "$query" "$target"
    else
        find "$target" -name .git -prune -o -type f -iname "*$query*" -print
    fi
}
