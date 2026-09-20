# Shell-kit

Small terminal conveniences for macOS and Linux, with Bash or Zsh. Keep changes
focused. Prefer shell builtins, standard Unix utilities and native tmux features.
The installer must run on Bash 3.2; no associative arrays, GNU-only flags, or
assumed package managers. Vanilla mode must work without Python or a network.

## Setup on a new machine

Read README.md and skills/tmux-reference/SKILL.md. Locate the checkout without
assuming a username, device, network address, or directory layout. Inspect the
active shell, login profile, ZDOTDIR, XDG_CONFIG_HOME, editor configs, symlinks,
and existing shortcuts. Preserve and incorporate existing configuration; never
copy whole dotfiles from another machine or publish their contents.

Run `bash install.sh` for interactive component selection. For agent-driven
setup, use `--components helpers,references,skill --mode vanilla --dry-run` as
an example starting point, adjusting the complete selection to the owner's
request. Use `--yes` only for an authorized selection. The manager checks tools;
never assume Brew, apt, sudo, Python, or network access. Enhanced display is
optional and any pip installation must be included in the approved plan.

## Ownership and checks

- install.sh owns marked source blocks, the runtime command links, and its local
  install.tsv manifest. Never source the manifest as shell code. Unselected
  foreign files and links must remain untouched.
- vanilla/ contains the shell implementations. bin/ retains optional enhanced
  display and picker implementations; bin/cheat keeps the stable entrypoint for
  existing installs. integrations/ is shared between modes.
- Keep backups and per-file replacement safety. Preserve dotfile symlinks and
  modes. Validate the entire config plan before writing any user config.
- Tests use temporary HOME directories and isolated tmux sockets. Never run a
  test against the owner's live configs/server or install dependencies silently.
- Run `python3 -B tests/run_all.py` before proposing a change; it runs every
  suite this machine supports and skips the rest with a reason. Name fragments
  select a subset (`run_all.py install`) while iterating. Report which OS and
  Bash versions were exercised, and never treat a skip as a pass.
- Do not weaken privacy, error handling, terminal cleanup, or meaningful checks
  to shorten the code. Do not add services, daemons or configuration frameworks.

- `configs` belongs to Helpers. Its Bash/awk scanner must never evaluate/source
  inspected files. Preserve unresolved markers and terminal-safe file links;
  do not promise a static scan reproduces arbitrary shell execution. Run
  `python3 -B tests/configs_check.py` for scanner changes (also accepts
  `SHELL_KIT_TEST_BASH`). Shell metadata comes from the interactive wrapper.
