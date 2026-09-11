# Existing portable Python helpers

`homelab-shell/scripts/` preserves four existing utility and test files from
Will's `homelab-shell` project, copied on 2026-09-10. The source directory had
no Git history. Existing code attribution and comments are intact.

The snapshot includes the names-only secret assignment auditor, the
dry-run-first assignment tidier, and their isolated tests. Both programs take
explicit file arguments and use Python's standard library. No machine names,
network addresses, credentials, SSH configuration, shell startup files, session
logs, or old cheat-sheet code were imported. Test credential strings are
synthetic canaries.

These files are preserved for reuse; the shell-kit installer does not install
this legacy bundle or replace existing live links. To read their usage:

```sh
python3 -B legacy/homelab-shell/scripts/audit_secrets.py --help
python3 -B legacy/homelab-shell/scripts/tidy_secrets.py --help
```

Run the retained isolated tests from the shell-kit repository:

```sh
python3 -B -m unittest discover -s legacy/homelab-shell/scripts -p 'test*.py'
```

Existing shell utilities were inventoried by filename. The machine-specific
homelab commands, launchers, backup jobs, and configuration belong to their
existing projects and are excluded from this portable collection.
