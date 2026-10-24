# AeroNox

*Coordinated low-light themes for Linux developer tools.*

AeroNox is an early-stage, offline Linux theme manager for Terminator, htop,
Vim and Visual Studio Code. **Roadmap stages 1–3 are implemented: foundation, safety engine and Terminator.**
The CLI inspects palettes, installs dedicated Terminator profiles with backups,
and opens new Terminator instances using a selected profile. htop, Vim and VS Code
integrations and active-theme management are still pending.

## Requirements and installation

Python 3.11+ on Linux, with ConfigObj 5.x (installed as a package dependency).
Terminator must already be installed to use its integration. From a local checkout,
install in user space:

```bash
pipx install .
# Alternatively: uv tool install .
```

No sudo, application installation, runtime network access or telemetry is needed.
Installing Python dependencies requires access to a package index unless cached.
The palettes are bundled in wheels; running outside the repository is supported.

## Available commands

```bash
aeronox --help
aeronox --version
aeronox doctor
aeronox palette list
aeronox palette show aviation-red
aeronox palette show nvis-green-a
aeronox palette contrast
aeronox install --dry-run
aeronox install --dry-run --components terminator,vim
aeronox install --components terminator
aeronox install --components terminator --base-profile 'My Profile' --dry-run
aeronox open terminator
aeronox open terminator --palette aviation-red
aeronox open terminator --palette nvis-green-a --dry-run
aeronox backup list
python scripts/report_contrast.py
```

`doctor` checks executable availability on PATH, platform and the COLORTERM hint.
It does not execute applications, inspect private configs, determine app versions,
verify True Color, or detect prepared VS Code profiles yet. Missing apps are reported
without failing the whole diagnostic. User-specific paths are omitted from output.
Unknown commands and arguments fail with a nonzero exit code.

`install --dry-run` shows target paths and planned byte counts without writing files
or launching applications. Real installation creates two dedicated profiles, leaves
the Terminator default and personal sections byte-identical, and snapshots the full
original config before changes. Missing applications are skipped; htop, Vim and
VS Code adapters are reported as pending. Recognized Snap/Flatpak Terminator paths
require manual setup. `backup list` reads private journals without creating state.

`open terminator --palette ...` verifies the installed profiles and launches with a
list of arguments, without a shell. It affects that new instance only and does not
persist an active theme. Arguments after `--` pass through individually. Without
an override, the initial `original` mode starts Terminator normally. No aliases or
shell configuration changes are made. See [application notes](docs/apps.md) for
base-profile selection, cursor/version limits and existing-window behavior.

## Palette preview

These are exact starting values from `palettes/*.json`, not application screenshots.

| Role | Aviation Red | NVIS Green A (inspired) |
| --- | --- | --- |
| Background | `#050000` | `#000500` |
| Foreground | `#CC3333` | `#66BB66` |
| Accent | `#FF4545` | `#88DD88` |
| Cursor | `#DD3333` | `#66CC77` |

Schema version 1 requires stable IDs, seven semantic roles, nonempty metadata and
exactly sixteen ANSI colors in `#RRGGBB` form. Unknown fields are rejected. Runtime
validation is implemented in `models.py`; JSON files remain the single source of
truth, packaged without generated duplicate copies. `palette contrast` reports
sRGB foreground/background contrast; it does not claim an accessibility rating.
Monochromatic ANSI colors lose conventional red/green semantics: use explicit text
or icons for errors, success and other critical signals.

## Safety and roadmap limits

XDG_CONFIG_HOME, XDG_STATE_HOME and XDG_DATA_HOME are resolved without creating
anything. Empty or relative XDG values fall back to the standard HOME locations.
No real user configuration is used as a test fixture.

The internal safety engine now supports exact target whitelists, immutable plans,
versioned ownership manifests, SHA-256 conflict checks, private snapshots, atomic
writes, writer locking and conservative rollback. Its mutation behavior is tested
only with synthetic resources in temporary HOME/XDG trees. Changes to generated
profiles cause conflicts; unrelated personal sections can be edited independently.
Every planned shared-file edit is checked for preservation of personal bytes. Symlinks,
hardlinks, special files, unsupported metadata and external XDG roots are refused.
See [safety and recovery](docs/safety-and-restore.md) for limits and recovery steps,
and [architecture](docs/architecture.md) for module responsibilities.

`apply`, `current`, `restore`, public `uninstall` and launchers for other apps remain
future commands. The Terminator adapter has a tested internal section-removal plan.
The safety engine initially records mode `original`; there is no active-theme
restore through the CLI yet. Manifest schema 1 is read for compatibility; the first
actual mutation snapshots it and writes schema 2 with per-profile ownership. An interrupted transaction may require manual
recovery from its private journal; automatic crash recovery is not implemented.
The Terminator default profile, shell startup files, `.vimrc` and VS Code Default
will remain protected. VS Code integration in the MVP will be assisted/manual;
changing already-open windows is outside the MVP scope. htop cannot promise exact
RGB correspondence. See [SPEC.md](SPEC.md) for the full roadmap and acceptance criteria.

The palettes are inspired by aviation lighting. They are **not NVIS certified**,
do not guarantee compatibility with night-vision equipment, and carry no proven
medical or ophthalmological benefit. Display brightness and environment matter.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/pytest
.venv/bin/python -m build
```

Tests isolate HOME and XDG directories in temporary locations, including paths with
spaces. CI tests Python 3.11–3.14 on Ubuntu and smoke-tests an installed wheel outside
the checkout. A smoke suite without pytest is also available after installing the package:
`python -m unittest discover -s tests -p test_smoke.py -v`.

The safety tests also run without pytest:
`python -m unittest discover -s tests -p test_backup_restore.py -v`.
They cover conflicts, permissions, symlinks, locks and injected failures.
Terminator integration tests run with
`python -m unittest discover -s tests -p test_terminator.py -v`.
They cover lossless parsing, native profile generation, shared-file ownership and
mocked launches without opening a GUI. Real visual validation and the full MVP E2E
scenarios remain pending; the full MVP acceptance criteria are not yet satisfied.

## Instruções rápidas (PT-BR)

Instale com `pipx install .` e consulte `aeronox doctor`. Para o Terminator, comece
com `aeronox install --components terminator --dry-run`; a instalação real usa o
mesmo comando sem `--dry-run`, cria backups e preserva o `default`. Abra uma nova
instância com `aeronox open terminator --palette aviation-red`. Isso não altera
janelas existentes nem persiste um tema ativo. Não foram usadas configurações
reais nos testes. htop, Vim, VS Code e restauração do tema continuam pendentes.

## License

MIT is proposed in the specification. The license choice must be confirmed before
publication; this foundation does not declare a license grant.
