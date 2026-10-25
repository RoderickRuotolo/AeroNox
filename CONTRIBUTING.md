# Contributing

Read SPEC.md and AGENTS.md before changing behavior. Keep changes small, typed and
reversible; Python code and primary docs use English. Palette colors belong only
in palettes/*.json. Regenerate VS Code examples after palette/generator changes.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/pytest
.venv/bin/python scripts/generate_vscode_assets.py --check
.venv/bin/python -m build
```

Tests must use temporary HOME/XDG roots and synthetic fixtures, never developer
dotfiles. Native Vim/htop checks are isolated; do not open a user's real GUI as part
of tests. Missing native applications can skip only their optional smoke tests.
Use failure injection for new mutations, including concurrent user edits and
rollback failure paths. Never add shell=True or sudo-based installation.

When pytest is unavailable, selected unittest suites can run after installing the
checkout, for example `python -m unittest discover -s tests -p test_lifecycle.py -v`.
This is useful fallback evidence, not a substitute claim that pytest/ruff passed.
Record actual checks and limitations in reviews. Review docs/acceptance.md before
claiming MVP acceptance or release readiness.

## Reports and compatibility

Report Python/Linux versions, application edition/version and the command/exit
status. Include sanitized synthetic reproductions; do not upload complete personal
configs, process listings, tokens or backup contents. Doctor hides paths by default;
review optional --paths output before sharing it. Version probes are explicit via
--versions and print only a parsed version, not arbitrary program output.

VS Code is assisted in this MVP. Never rewrite Default or internal profile IDs;
unknown layouts should fail closed with manual instructions. Preserve Terminator
default bytes and user preference semantics. Generated resources edited by the
user or application must not be silently overwritten or deleted.

The project's license choice remains to be confirmed before release publication;
no unconfirmed license grant is introduced by this guide.
