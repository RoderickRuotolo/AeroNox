# AeroNox

*Coordinated low-light themes for Linux developer tools.*

AeroNox is an early-stage, offline Linux theme manager for Terminator, htop,
Vim and Visual Studio Code. **Only roadmap stage 1 (foundation) is implemented.**
It currently inspects palettes and reports application availability. It does not
install themes, launch applications, persist an active palette or change user files.

## Requirements and installation

Python 3.11+ on Linux. From a local checkout, install in user space:

```bash
pipx install .
# Alternatively: uv tool install .
```

No sudo, application installation, runtime network access or telemetry is needed.
Development dependency installation requires access to a package index unless cached.
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
python scripts/report_contrast.py
```

`doctor` checks executable availability on PATH, platform and the COLORTERM hint.
It does not execute applications, inspect private configs, determine app versions,
verify True Color, or detect prepared VS Code profiles yet. Missing apps are reported
without failing the whole diagnostic. User-specific paths are omitted from output.
Unknown commands and arguments fail with a nonzero exit code.

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

`install`, `--dry-run`, `apply`, `current`, `open`, `backup`, `restore` and `uninstall`
are future commands, intentionally unavailable in this foundation release. There
is no theme state to restore yet. Later stages will add plans, conflict detection,
backups, atomic writes and rollback before implementing application integrations.
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
the checkout. A dependency-free smoke suite is also available after installing the package:
`python -m unittest discover -s tests -p test_smoke.py -v`.

Integration and adversarial storage tests belong to later roadmap
stages; the full MVP acceptance criteria are not yet satisfied.

## Instruções rápidas (PT-BR)

Instale com `pipx install .`, consulte `aeronox doctor` e visualize as paletas com
`aeronox palette show aviation-red`. Esta etapa não aplica temas nem modifica
configurações. Os comandos de instalação, restauração e abertura virão depois.

## License

MIT is proposed in the specification. The license choice must be confirmed before
publication; this foundation does not declare a license grant.
