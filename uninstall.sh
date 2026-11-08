#!/usr/bin/env bash
# Bash 3.2-compatible uninstaller for shell-kit.
# Removes shell-kit managed blocks from user configuration files and cleans runtime links.
set -euo pipefail
SELF=$0
while [ -L "$SELF" ]; do
    target=$(readlink "$SELF")
    case $target in /*) SELF=$target ;; *) SELF=$(dirname "$SELF")/$target ;; esac
done
ROOT=$(cd -P -- "$(dirname "$SELF")" && pwd)
exec "$ROOT/install.sh" --uninstall "$@"
