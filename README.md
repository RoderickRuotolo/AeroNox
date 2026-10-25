# AeroNox

*Coordinated low-light themes for Linux developer tools.*

AeroNox is an early-stage, offline Linux theme manager for Terminator, htop,
Vim and Visual Studio Code. **All six roadmap implementation stages are present (MVP).**
The CLI inspects palettes, installs isolated Terminator/htop/Vim resources and
generates assisted VS Code snippets with backups and conflict checks. VS Code
profile setup is manual. Active-mode control and conservative removal are available;
[acceptance/release gates](docs/acceptance.md) remain explicit.

## Requirements and installation

Python 3.11+ on Linux, with ConfigObj 5.x (installed as a package dependency).
Each target application must already be installed to use its integration. From a
local checkout, install in user space:

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
aeronox doctor --paths
aeronox doctor --versions
aeronox palette list
aeronox palette show aviation-red
aeronox palette show nvis-green-a
aeronox palette contrast
aeronox install --dry-run
aeronox install --dry-run --components terminator,vim
aeronox install --components terminator
aeronox install --components htop,vim --dry-run
aeronox install --components htop,vim
aeronox install --components terminator --base-profile 'My Profile' --dry-run
aeronox apply aviation-red --dry-run
aeronox apply aviation-red
aeronox current
aeronox open terminator
aeronox open terminator --palette aviation-red
aeronox open terminator --palette nvis-green-a --dry-run
aeronox open htop --palette aviation-red
aeronox open htop --palette nvis-green-a --dry-run
aeronox open vim --palette nvis-green-a -- README.md
aeronox install --components vscode --dry-run
aeronox vscode guide
aeronox vscode snippet aviation-red
aeronox vscode status --edition stable
# Only after manually preparing the dedicated profile:
aeronox open code --edition stable --palette aviation-red -- /path/to/project
aeronox apply nvis-green-a
aeronox backup list
aeronox restore --dry-run
aeronox restore
aeronox uninstall --dry-run
aeronox uninstall
python scripts/report_contrast.py
```

`doctor` checks executable availability on PATH, platform and the COLORTERM hint.
It also performs read-only VS Code edition/profile checks. By default it executes
no applications and does not probe versions or verify True Color. `--versions`
explicitly requests bounded native --version probes and prints parsed version
numbers only; `--paths` opts into local config/resource paths. It reads profile metadata and
only dedicated VS Code settings; Default settings are never inspected. Missing apps are reported
without failing the whole diagnostic. User-specific paths are omitted from output.
Unknown commands and arguments fail with a nonzero exit code.

`install --dry-run` shows target paths and planned byte counts without writing files
or launching applications. Real installation creates two dedicated profiles, leaves
the Terminator default and personal sections byte-identical, and snapshots the full
original config before changes. htop uses separate per-palette htoprc copies, and
Vim uses colorschemes under XDG data without editing `.vimrc`. Missing applications
are skipped. VS Code installation generates reference snippets only; the user
must manually merge them into dedicated profiles. Recognized Snap/Flatpak paths
require manual setup. Component transactions are independent: a later failure
reports earlier committed components and backup IDs instead of hiding them.
`backup list` reads private journals without creating state.

`open <application> --palette ...` verifies installed resources and launches with a
list of arguments, without a shell. It affects that new instance only and does not
change the persisted mode when a per-launch --palette override is used. Arguments
after `--` pass through individually. `apply` persists the default for later wrapper
launches without regenerating configs or changing already-open windows. Without
an override, the initial `original` mode starts Terminator/htop/Vim normally. Code
instead prints setup instructions to avoid accidentally creating/selecting an
unprepared profile; explicit `--palette original` opts into ordinary Code launch.
No aliases or
shell configuration changes are made. See [application notes](docs/apps.md) for
base-profile selection, cursor/version limits and existing-window behavior.

htop uses native monochrome (`-C`) and an isolated `HTOPRC`; exact RGB matching is
not promised. Run it inside a themed Terminator to inherit that terminal's colors.
Its history is redirected to a per-palette XDG state root. If htop rewrites the
managed htoprc, later use/install/removal reports a conflict and preserves it;
automatic reconciliation is not implemented yet. Vim includes RGB and approximate
xterm-256 highlights, including bold/reverse/underline cues. True Color depends on
the user's terminal and Vim settings; the wrapper does not force it on.

## Assisted VS Code setup

Read the [offline setup guide](assets/vscode/GUIDE.md) or run `aeronox vscode guide`.
Create **AeroNox Aviation Red** and **AeroNox NVIS Green A** profiles manually,
with independent settings, then merge the corresponding snippet objects. Preserve
unrelated settings and never replace the entire settings.json. Only generated
reference files are installed under AeroNox XDG data; no VS Code settings, registry
or Default profile is modified. `--profile` alone does not import a theme.

`vscode status` distinguishes snippets from prepared profiles. Native Stable,
Insiders and VSCodium use separate roots; Snap/Flatpak/portable packages are
reported as manual setup/launch. `open code` verifies existing named profiles
before using --profile, and refuses missing, ambiguous or unsafe layouts. It does
not promise automatic updates to already-open windows. See [VS Code limits and
checks](docs/vscode.md) for custom data roots, JSONC and the verification race limit.

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

`current` prints `original` if no state exists. `apply <palette>` changes only the
active mode; `restore` returns it to `original` without changing app resources.
Both mode changes use private snapshots and atomic state writes. Repeating the
same mode does not create more backups. Missing integrations remain actionable
at launch rather than being silently installed.

`uninstall` combines all known adapter removal plans and the mode reset in one
transaction. Any modified/unsafe resource or unknown ownership destination aborts
the whole operation with no removals; use `restore` independently to stop themed
wrapper launches. Terminator's personal sections and all manual Code profiles are
preserved. Backups, state/recovery data, runtime histories and empty directories
are retained. This removes resources, not the installed Python package; remove
that separately through the tool used to install it if desired.

Manifest schema 1 is read for compatibility; the first actual mutation snapshots
it and writes schema 2. Interrupted transactions may require manual recovery from
private journals; automatic crash recovery and bulk backup restore are not included.
The Terminator default profile, shell startup files, `.vimrc` and VS Code Default
will remain protected. VS Code integration in the MVP will be assisted/manual;
changing already-open windows is outside the MVP scope. htop cannot promise exact
RGB correspondence. See [SPEC.md](SPEC.md) for the full roadmap and acceptance criteria.

The palettes are inspired by aviation lighting. They are **not NVIS certified**,
do not guarantee compatibility with night-vision equipment, and carry no proven
medical or ophthalmological benefit. Display brightness and environment matter.

## Native previews

[Four real terminal recordings](docs/screenshots/README.md) show native Vim and htop
in isolated pseudoterminals with synthetic input and AeroNox terminal theme metadata.
Vim recordings contain real RGB output; htop uses native monochrome. These can be
played offline with an asciicast-compatible player. Desktop GUI screenshots and
final visual checks remain manual acceptance items.

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
mocked launches without opening a GUI. htop/Vim tests are available through
`python -m unittest discover -s tests -p test_htop.py -v` and
`python -m unittest discover -s tests -p test_vim.py -v`.
When native executables are available, these render htop controls in a temporary
PTY and load both Vim themes headlessly with and without True Color. Missing
native binaries cause those particular smoke tests to skip. Real desktop visual
validation remains pending. Installed-CLI E2E tests cover red → green → restore →
uninstall and preservation of personal files; lifecycle tests inject failures and
concurrent edits. Run them without pytest using
`python -m unittest discover -s tests -p test_lifecycle.py -v` and
`python -m unittest discover -s tests -p test_e2e.py -v`.
See [acceptance status](docs/acceptance.md) for remaining gates. VS Code/JSONC tests can run with
`python -m unittest discover -s tests -p test_vscode.py -v` and
`python -m unittest discover -s tests -p test_jsonc.py -v`.
Generated reference snippets are checked with
`python scripts/generate_vscode_assets.py --check`.

## Instruções rápidas (PT-BR)

Instale com `pipx install .` e consulte `aeronox doctor`. Para o Terminator, comece
com `aeronox install --components terminator --dry-run`; a instalação real usa o
mesmo comando sem `--dry-run`, cria backups e preserva o `default`. Abra uma nova
instância com `aeronox open terminator --palette aviation-red`. Isso não altera
janelas existentes; o argumento `--palette` vale apenas para essa abertura. Não foram usadas configurações
reais nos testes. htop e Vim também estão disponíveis: instale com
`aeronox install --components htop,vim --dry-run` e depois sem `--dry-run`.
Abra com `aeronox open htop --palette aviation-red` ou
`aeronox open vim --palette nvis-green-a -- README.md`. O htop usa monocromia e
pode regravar a cópia, causando um conflito conservador. Para VS Code, consulte
`aeronox vscode guide`, crie os perfis dedicados e mescle os snippets manualmente.
`aeronox vscode status` verifica a preparação sem alterar configurações; somente
então use `aeronox open code --palette aviation-red`. O perfil Default nunca é
reescrito. Use `aeronox apply aviation-red` para selecionar a paleta das próximas
aberturas, `aeronox current` para consultar e `aeronox restore` para voltar ao modo
original sem reescrever preferências. `aeronox uninstall --dry-run` mostra a remoção
conservadora; sem o flag, a remoção só ocorre quando todos os recursos estão intactos.

## License

MIT is proposed in the specification. The license choice must be confirmed before
publication; this foundation does not declare a license grant.
