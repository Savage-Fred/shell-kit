#!/usr/bin/env bash
# Bash 3.2-compatible uninstaller for shell-kit.
# Removes shell-kit managed blocks from user configuration files and cleans runtime links.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd -P)
exec "$ROOT/install.sh" --uninstall "$@"
