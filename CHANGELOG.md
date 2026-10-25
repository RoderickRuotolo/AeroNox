# Changelog

## Unreleased — v0.1 MVP implementation

- Python CLI, validated central palettes and XDG resolution.
- Snapshot-first transactions, private backup journals, ownership/conflict checks,
  atomic file replacement and conservative rollback.
- Lossless Terminator profiles, separate monochrome htop configs and RGB/256-color
  Vim schemes; launch arguments remain separate without a shell.
- Assisted VS Code snippets, offline setup guide, edition detection and read-only
  existing-profile checks without rewriting Default.
- apply/current/restore persist only mode; existing windows stay unchanged.
- Atomic uninstall removes only intact known resources, preserves personal configs,
  manual Code profiles, runtime history and backup/recovery data.
- Lifecycle/E2E/adversarial tests, native terminal recordings, CI and acceptance docs.

Desktop GUI checks, complete development-tool verification in the target environment
and license confirmation remain release gates. See docs/acceptance.md for scope.
