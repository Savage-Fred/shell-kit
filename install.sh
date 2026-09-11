#!/usr/bin/env bash
# Bash 3.2-compatible component manager. No package manager is invoked.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd -P)
STATE="$HOME/.local/state/shell-kit"
LINK="$HOME/.local/share/shell-kit"
RUNTIME="$HOME/.local/share/shell-kit-runtime/bin"
names=(helpers references tmux vim skill)
labels=('Shell search helpers' 'References and shell F1-F4 keys' 'Tmux keys and session picker' 'Vim / Neovim references' 'Agent reference skill')
selected=(0 0 0 0 0)
mode=vanilla
yes=0 dry=0 interactive=1 uninstall=0
old_files=() old_markers=()
paths=() markers=() bodies=() targets=() staged=()
link_paths=() link_sources=()
previous_root=$ROOT
if [ -L "$LINK" ] && { [ -f "$STATE/install.tsv" ] || [ -f "$LINK/integrations/shell.sh" ]; }; then previous_root=$(readlink "$LINK"); fi
terminal='' pending=''
work=$(mktemp -d "${TMPDIR:-/tmp}/shell-kit-install.XXXXXX")
cleanup() {
    if [ -n "$terminal" ]; then stty "$terminal" < /dev/tty; printf '\033[?25h' > /dev/tty; fi
    if [ -n "$pending" ]; then rm -f "$pending"; fi
    rm -rf "$work"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
die() { printf '%s\n' "$*" >&2; exit 1; }
has() { command -v "$1" >/dev/null 2>&1; }
chosen() { [ "${selected[$1]}" = 1 ]; }

if [ -f "$STATE/install.tsv" ]; then
    while IFS=$'\t' read -r kind value extra; do
        case $kind in
            mode) case $value in vanilla|enhanced) mode=$value;; *) die 'Invalid saved mode';; esac ;;
            component) for i in 0 1 2 3 4; do [ "$value" != "${names[$i]}" ] || selected[$i]=1; done ;;
            file) old_markers[${#old_markers[@]}]=$value; old_files[${#old_files[@]}]=$extra ;;
        esac
    done < "$STATE/install.tsv"
elif [ -L "$LINK" ] && [ -f "$LINK/integrations/shell.sh" ]; then
    # Adopt the earlier all-components installation, without running its Python.
    selected=(1 1 1 1 1)
    mode=enhanced
fi
while [ "$#" -gt 0 ]; do
    case $1 in
        --components)
            [ "$#" -ge 2 ] || die '--components needs a comma-separated list'
            selected=(0 0 0 0 0); interactive=0
            IFS=, read -r -a requested <<< "$2"
            for name in "${requested[@]}"; do
                found=0
                for i in 0 1 2 3 4; do
                    if [ "$name" = "${names[$i]}" ]; then selected[$i]=1; found=1; fi
                done
                [ "$found" = 1 ] || die "Unknown component: $name"
            done
            shift ;;
        --mode) [ "$#" -ge 2 ] || die '--mode needs vanilla or enhanced'; mode=$2; shift ;;
        --yes) yes=1 ;;
        --dry-run) dry=1; interactive=0 ;;
        --uninstall) uninstall=1; interactive=0 ;;
        --help|-h)
            cat <<'HELP'
Usage: bash install.sh
  Arrows move; Space selects; m switches vanilla/enhanced; Enter previews;
  y confirms the displayed plan; q cancels. Unchecked components are removed.

For agents: --components helpers,references,tmux,vim,skill
            --mode vanilla|enhanced --dry-run | --yes
Remove managed integrations: --uninstall [--dry-run | --yes]

Vanilla uses Bash and standard Unix tools. less is optional (cat fallback).
Tmux and Vim/Neovim are required only for their selected integrations.
Enhanced references need Python 3 and Rich; the enhanced picker needs fzf.
Missing Rich is offered as a private venv/pip install in the confirmation plan.
HELP
            exit 0 ;;
        *) die "Unknown option: $1 (see --help)" ;;
    esac
    shift
done
case $mode in vanilla|enhanced) ;; *) die 'Mode must be vanilla or enhanced';; esac
if [ "$uninstall" = 1 ]; then selected=(0 0 0 0 0); fi
if chosen 2 || chosen 3; then selected[1]=1; fi

dependencies() {
    local failed=0 tool version
    for tool in awk cat cmp cp dirname grep ln mkdir mktemp mv readlink rm tail; do
        if ! has "$tool"; then printf 'Missing standard tool: %s\n' "$tool"; failed=1; fi
    done
    if chosen 2; then
        if ! has tmux; then printf 'Tmux component needs tmux >=3.2.\n'; failed=1
        else
            version=$(tmux -V)
            if ! printf '%s\n' "$version" | awk '{split($2,v,"."); exit !(v[1]>3 || (v[1]==3 && v[2]+0>=2))}'; then
                printf 'Tmux >=3.2 required; found %s.\n' "$version"; failed=1
            fi
        fi
        if [ "$mode" = enhanced ] && ! has fzf; then printf 'Enhanced picker needs fzf; vanilla uses tmux choose-tree.\n'; failed=1; fi
    fi
    if chosen 3 && ! has vim && ! has nvim; then printf 'Editor component needs Vim or Neovim.\n'; failed=1; fi
    if [ "$mode" = enhanced ] && chosen 1; then
        for tool in python3 less; do
            if ! has "$tool"; then printf 'Enhanced references need %s; choose vanilla to avoid it.\n' "$tool"; failed=1; fi
        done
    fi
    if chosen 0; then
        for tool in grep find sort; do
            if ! has "$tool"; then printf 'Shell helpers need %s.\n' "$tool"; failed=1; fi
        done
    fi
    return "$failed"
}

if [ "$interactive" = 1 ]; then
    [ -t 0 ] && [ -t 1 ] || die 'Use a terminal, or --components with --dry-run / --yes.'
    has stty || die 'Interactive selection needs stty; use --components instead.'
    terminal=$(stty -g < /dev/tty)
    stty -echo -icanon min 1 time 0 < /dev/tty
    printf '\033[?25l'
    cursor=0
    while :; do
        printf '\033[H\033[2JShell-kit component manager\n\n'
        for i in 0 1 2 3 4; do
            pointer=' '; check=' '
            [ "$cursor" != "$i" ] || pointer='>'
            [ "${selected[$i]}" != 1 ] || check=x
            printf '%s [%s] %s\n' "$pointer" "$check" "${labels[$i]}"
        done
        printf '\nMode: %s (m switches)\n' "$mode"
        printf 'Vanilla: plain Markdown, manual help, native tmux picker; no Python.\n'
        printf 'Enhanced: Rich rendering, automatic sidebars, fzf picker.\n\n'
        printf 'Dependencies already available:'
        for tool in tmux vim nvim less python3 fzf; do has "$tool" && printf ' %s' "$tool"; done
        printf '\nPackage managers available:'
        for tool in brew apt-get; do has "$tool" && printf ' %s' "$tool"; done
        printf ' (never run automatically)\n\n'
        dependencies || :
        printf '\nArrows move | Space selects | Enter previews | q cancels\n'
        IFS= read -r -s -n 1 key || exit 0
        case $key in
            $'\033')
                suffix=''; IFS= read -r -s -n 2 -t 1 suffix || :
                case $suffix in '[A'|'OA'|'[D'|'OD') cursor=$(( (cursor + 4) % 5 ));; '[B'|'OB'|'[C'|'OC') cursor=$(( (cursor + 1) % 5 ));; esac ;;
            ' ')
                selected[$cursor]=$((1 - selected[$cursor]))
                if [ "$cursor" = 1 ] && ! chosen 1; then selected[2]=0; selected[3]=0; fi
                if chosen 2 || chosen 3; then selected[1]=1; fi ;;
            m|M) if [ "$mode" = vanilla ]; then mode=enhanced; else mode=vanilla; fi ;;
            q|Q) exit 0 ;;
            '') if dependencies >/dev/null; then break; fi ;;
        esac
    done
    stty "$terminal" < /dev/tty
    printf '\033[?25h'
    terminal=''
fi
dependencies || die 'Nothing changed. Select fewer components or choose --mode vanilla.'

# Resolve existing dotfile symlinks so replacement preserves the user's links.
resolve() {
    local path=$1 dest count=0
    while [ -L "$path" ]; do
        count=$((count + 1)); [ "$count" -le 40 ] || die "Symlink loop: $1"
        dest=$(readlink "$path")
        case $dest in /*) path=$dest;; *) path=$(dirname "$path")/$dest;; esac
    done
    if [ -d "$(dirname "$path")" ]; then path=$(cd "$(dirname "$path")" && pwd -P)/${path##*/}; fi
    printf '%s\n' "$path"
}
writable_parent() {
    local parent
    parent=$(dirname "$1")
    while [ ! -e "$parent" ]; do parent=$(dirname "$parent"); done
    [ -d "$parent" ] && [ -w "$parent" ]
}
add_file() {
    local i path=$1
    case $path in /*) ;; *) path="$PWD/$path";; esac
    for ((i=0; i<${#paths[@]}; i++)); do
        if [ "${paths[$i]}" = "$path" ]; then markers[$i]=$2; bodies[$i]=$3; return; fi
    done
    paths[${#paths[@]}]=$path; markers[${#markers[@]}]=$2; bodies[${#bodies[@]}]=$3
}
# Remove old blocks even if the user's config locations changed since last run.
for ((i=0; i<${#old_files[@]}; i++)); do add_file "${old_files[$i]}" "${old_markers[$i]}" ''; done
for path in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.tmux.conf" "$HOME/.vimrc" "$HOME/.config/nvim/init.vim" "$HOME/.config/nvim/init.lua"; do
    marker='#'
    case $path in */.vimrc|*/init.vim) marker='"';; */init.lua) marker='--';; esac
    if [ -f "$path" ] && grep -Fq "$marker BEGIN SHELL-KIT" "$path"; then add_file "$path" "$marker" ''; fi
done
components=''
for i in 0 1 2 3 4; do chosen "$i" && components="$components ${names[$i]}"; done
if chosen 0 || chosen 1 || chosen 2; then
    body='if [ -n "${BASH_VERSION-}${ZSH_VERSION-}" ]; then
'"export SHELL_KIT_COMPONENTS='$components '"$'\n''[ -r "$HOME/.local/share/shell-kit/integrations/shell.sh" ] && . "$HOME/.local/share/shell-kit/integrations/shell.sh"
fi'
    add_file "$HOME/.bashrc" '#' "$body"
    add_file "${ZDOTDIR:-$HOME}/.zshrc" '#' "$body"
    login="$HOME/.bash_profile"
    for path in "$HOME/.bash_profile" "$HOME/.bash_login" "$HOME/.profile"; do
        if [ -e "$path" ]; then login=$path; break; fi
    done
    # Source our guarded integration directly; never re-source the user's bashrc.
    add_file "$login" '#' "$body"
fi
if chosen 2; then
    path="$HOME/.tmux.conf"
    if [ ! -e "$path" ] && [ -f "${XDG_CONFIG_HOME:-$HOME/.config}/tmux/tmux.conf" ]; then path="${XDG_CONFIG_HOME:-$HOME/.config}/tmux/tmux.conf"; fi
    add_file "$path" '#' 'source-file -q ~/.local/share/shell-kit/integrations/tmux.conf'
fi
if chosen 3; then
    path="$HOME/.vimrc"
    if [ ! -e "$path" ] && [ -f "$HOME/.vim/vimrc" ]; then path="$HOME/.vim/vimrc"; fi
    add_file "$path" '"' 'source ~/.local/share/shell-kit/integrations/vim.vim'
    path="${XDG_CONFIG_HOME:-$HOME/.config}/nvim"
    if [ -f "$path/init.lua" ]; then
        add_file "$path/init.lua" '--' "vim.cmd('source ' .. vim.fn.fnameescape(vim.fn.expand('~/.local/share/shell-kit/integrations/vim.vim')))"
    else add_file "$path/init.vim" '"' 'source ~/.local/share/shell-kit/integrations/vim.vim'; fi
fi

add_link() { link_paths[${#link_paths[@]}]=$1; link_sources[${#link_sources[@]}]=$2; }
source_root="$ROOT/vanilla"
if [ "$mode" = enhanced ]; then source_root="$ROOT/bin"; fi
source=''
if chosen 1; then
    source="$source_root/cheat"
    [ "$mode" != enhanced ] || source="$ROOT/bin/cheat-enhanced"
fi
add_link "$RUNTIME/cheat" "$source"
source=''; chosen 0 && source="$ROOT/vanilla/shell-kit-search"; add_link "$RUNTIME/shell-kit-search" "$source"
source=''; chosen 2 && source="$source_root/tmenu"; add_link "$RUNTIME/tmenu" "$source"
for base in .agents/skills .codex/skills .claude/skills .gemini/skills .gemini/antigravity/skills; do
    source=''; chosen 4 && source="$ROOT/skills/tmux-reference"
    add_link "$HOME/$base/tmux-reference" "$source"
done
source=''; [ -z "$components" ] || source=$ROOT; add_link "$LINK" "$source"

# Stage and validate every file before modifying any user configuration.
for ((i=0; i<${#paths[@]}; i++)); do
    path=${paths[$i]}
    case $path in *$'\n'*|*$'\t'*) die 'Config paths cannot contain tabs or newlines';; esac
    target=$(resolve "$path"); targets[$i]=$target
    [ ! -e "$target" ] || [ -f "$target" ] || die "Not a regular config file: $path"
    writable_parent "$target" || die "Config directory is not writable: $path"
    staged[$i]="$work/$i"
    input=/dev/null; [ ! -f "$target" ] || input=$target
    if ! awk -v marker="${markers[$i]}" '
        $0 == marker " BEGIN SHELL-KIT" {if (inside || seen++) exit 42; inside=1; next}
        $0 == marker " END SHELL-KIT" {if (!inside) exit 42; inside=0; next}
        !inside {print}
        END {if (inside) exit 42}
    ' "$input" > "${staged[$i]}"; then die "Malformed managed block: $path"; fi
    if [ -n "${bodies[$i]}" ]; then
        printf '%s BEGIN SHELL-KIT\n%s\n%s END SHELL-KIT\n' "${markers[$i]}" "${bodies[$i]}" "${markers[$i]}" >> "${staged[$i]}"
    fi
    if [ -f "$target" ] && ! cmp -s "$target" "${staged[$i]}" && [ ! -w "$target" ]; then
        die "Config file is read-only: $path"
    fi
    for ((j=0; j<i; j++)); do
        if [ "${targets[$j]}" = "$target" ] && ! cmp -s "${staged[$j]}" "${staged[$i]}"; then
            die "Conflicting integrations share one file: ${paths[$j]} and $path"
        fi
    done
done
for ((i=0; i<${#link_paths[@]}; i++)); do
    path=${link_paths[$i]}
    if [ -e "$path" ] || [ -L "$path" ]; then
        owned=0
        if [ -L "$path" ]; then
            old=$(readlink "$path")
            case $old in
                "$ROOT"|"$previous_root"|"$ROOT"/bin/*|"$previous_root"/bin/*|"$ROOT"/vanilla/*|"$previous_root"/vanilla/*|"$ROOT"/skills/tmux-reference|"$previous_root"/skills/tmux-reference) owned=1 ;;
            esac
        fi
        if [ "$owned" = 0 ]; then
            # Unselected foreign components belong to the user, not this installer.
            if [ -z "${link_sources[$i]}" ]; then link_paths[$i]=''; continue; fi
            die "Refusing to replace existing path: $path"
        fi
    fi
    if ! writable_parent "$path"; then
        case $path in
            */skills/tmux-reference)
                printf 'Skip protected skill directory: %s\n' "$(dirname "$path")"
                link_paths[$i]='' ;;
            *) die "Install directory is not writable: $path" ;;
        esac
    fi
done
writable_parent "$STATE/install.tsv" || die "State directory is not writable: $STATE"
if chosen 4; then
    available=0
    for ((i=0; i<${#link_paths[@]}; i++)); do
        case ${link_paths[$i]} in */skills/tmux-reference) available=1;; esac
    done
    [ "$available" = 1 ] || die 'No writable skill discovery directory; deselect the skill component.'
fi

printf '\nProposed configuration: %s\n' "$mode"
for i in 0 1 2 3 4; do
    action=disabled; chosen "$i" && action=enabled
    printf '  %-12s %s\n' "${names[$i]}" "$action"
done
for ((i=0; i<${#paths[@]}; i++)); do
    if ! cmp -s "${targets[$i]}" "${staged[$i]}"; then printf '  Update %s\n' "${paths[$i]}"; fi
done
for ((i=0; i<${#link_paths[@]}; i++)); do
    path=${link_paths[$i]}; source=${link_sources[$i]}
    [ -n "$path" ] || continue
    if [ -L "$path" ] && [ "$(readlink "$path")" = "$source" ]; then continue; fi
    if [ -n "$source" ]; then printf '  Link %s -> %s\n' "$path" "$source"
    elif [ -L "$path" ]; then printf '  Remove link %s\n' "$path"; fi
done
setup_rich=0
if [ "$mode" = enhanced ] && chosen 1; then
    if ! "$ROOT/.venv/bin/python" -c 'import rich' >/dev/null 2>&1; then
        setup_rich=1
        printf '  Create/repair private .venv and install Rich using pip (network required).\n'
    fi
fi
printf 'Backups will be retained in %s/backups.\n' "$STATE"
if [ "$dry" = 1 ]; then exit 0; fi
if [ "$yes" != 1 ]; then
    [ -t 0 ] || die 'Nothing changed. Use --yes to apply a reviewed plan noninteractively.'
    printf 'Apply this plan? [y/N] '
    IFS= read -r -n 1 reply || exit 0
    printf '\n'
    case $reply in y|Y) ;; *) printf 'Cancelled; nothing changed.\n'; exit 0;; esac
fi
if [ "$setup_rich" = 1 ]; then
    python3 -m venv "$ROOT/.venv"
    "$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"
fi
mkdir -p "$STATE/backups"
backup=$(mktemp -d "$STATE/backups/install.XXXXXX")
for ((i=0; i<${#paths[@]}; i++)); do
    target=${targets[$i]}
    if cmp -s "$target" "${staged[$i]}"; then continue; fi
    if [ ! -e "$target" ] && [ ! -s "${staged[$i]}" ]; then continue; fi
    mkdir -p "$(dirname "$target")"
    temp=$(mktemp "$target.shell-kit.XXXXXX")
    pending=$temp
    if [ -f "$target" ]; then
        cp -p "$target" "$backup/$i"
        printf '%s\t%s\n' "$i" "$target" >> "$backup/files.tsv"
        cp -p "$target" "$temp"
    fi
    cat "${staged[$i]}" > "$temp"
    mv -f "$temp" "$target"
    pending=''
done
for ((i=0; i<${#link_paths[@]}; i++)); do
    path=${link_paths[$i]}; source=${link_sources[$i]}
    [ -n "$path" ] || continue
    if [ -L "$path" ]; then
        [ "$(readlink "$path")" != "$source" ] || continue
        rm "$path"
    fi
    if [ -n "$source" ]; then mkdir -p "$(dirname "$path")"; ln -s "$source" "$path"; fi
done
{
    printf 'mode\t%s\n' "$mode"
    for i in 0 1 2 3 4; do chosen "$i" && printf 'component\t%s\n' "${names[$i]}"; done
    for ((i=0; i<${#paths[@]}; i++)); do
        [ -z "${bodies[$i]}" ] || printf 'file\t%s\t%s\n' "${markers[$i]}" "${paths[$i]}"
    done
} > "$work/install.tsv"
mv "$work/install.tsv" "$STATE/install.tsv"
printf 'Saved. Backups: %s\nOpen a new shell/editor. Reload tmux config for added bindings.\n' "$backup"
printf 'Removed bindings already loaded in a running program clear on its next restart.\n'
