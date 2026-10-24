# Application integrations

## Terminator (stage 3)

The native Terminator executable must already be on PATH. AeroNox never installs
it. Missing applications are skipped with an actionable message; other components
remain pending in this release. Recognized Snap/Flatpak executable paths are
skipped because their configuration locations cannot be assumed. Detection uses
PATH without executing a version probe. Arbitrary launcher scripts and all
sandboxed packaging variants cannot be reliably classified from PATH alone.

Preview and install:

```bash
aeronox install --components terminator --dry-run
aeronox install --components terminator
# Clone a particular personal profile instead of default:
aeronox install --components terminator --base-profile 'My Profile' --dry-run
aeronox install --components terminator --base-profile 'My Profile'
```

The target is `${XDG_CONFIG_HOME:-~/.config}/terminator/config`. It is parsed as
ConfigObj, including nested sections and quoted/multiline values. A source index
locates sections so the original file is not serialized or reformatted. Duplicate
or malformed sections, non-UTF-8 text, NUL, CR-only line endings, unsupported
section syntax and nesting beyond 64 levels are refused. LF, CRLF and UTF-8 BOM
are supported. ConfigObj exception details are redacted because they may contain
private commands.

The two generated profiles are `AeroNox Aviation Red` and `AeroNox NVIS Green A`.
Existing profiles, `default`, global settings, keybindings, layouts, plugins and
unknown sections retain their original bytes. Only newly generated/owned blocks
are serialized. Fonts, cursor shape/blink, scrolling, custom commands and unknown
base settings are inherited. The base is `default` unless explicitly selected;
AeroNox does not infer a running window's active profile. With no user default,
new profiles omit those preferences and use Terminator's built-in defaults.
System-wide fallback configs are not imported.

Generated overrides are `use_theme_colors`, `foreground_color`, `background_color`,
`background_type = solid` and the central 16-color palette. Cursor overrides use
only cursor keys already present in the selected base: legacy `cursor_color`, or
`cursor_bg_color`/`cursor_fg_color`. Without such keys the cursor follows
Terminator's inherited/default behavior; exact cursor color is not guaranteed.
Other visual elements such as titlebar colors remain inherited. See the
[Terminator configuration manual](https://github.com/gnome-terminator/terminator/blob/master/doc/terminator_config.adoc)
for native option semantics.

An existing AeroNox name without registered section ownership causes a conflict,
even if its colors appear correct. AeroNox will not silently claim it or choose a
different name. Review/rename the existing profile yourself before retrying.

## Opening Terminator

```bash
aeronox open terminator
# Explicit palette for this invocation; does not persist an active theme:
aeronox open terminator --palette aviation-red
aeronox open terminator --palette nvis-green-a -- --working-directory '/tmp/my project'
# Inspect the exact argument vector without launching anything:
aeronox open terminator --palette aviation-red --dry-run
```

With active mode `original` (the initial state), the wrapper starts Terminator
normally. An explicit `--palette` overrides that mode for one launch only. Themed
launches first verify registered profiles, then use `--no-dbus --config <path>
--profile <name>` to load the selected configuration in a separate process.
Arguments after `--` are passed individually through subprocess without a shell.
The child's exit code is returned; the terminal is inherited. Arguments can include
Terminator's own command-launch flags, whose semantics remain Terminator's.

Installation changes no active palette and does not reload or recolor open
windows. Direct `terminator -p 'AeroNox Aviation Red'` also selects the profile;
an already-running process may need a restart to see newly installed profiles.
No aliases, PATH modifications, shell startup edits, desktop entries or background
watchers are created. `apply` and active-mode management are reserved for stage 6.

## Ownership and removal

Manifest schema 2 stores the raw SHA-256 of each generated profile separately from
the historical whole-file hash. Editing personal sections does not invalidate the
managed profiles. Reinstallation re-clones the selected current base, so changing
a personal font can update the generated copies without rewriting that base.
A change to a generated block, including whitespace/comments, is a conflict.
Terminator's GUI may reformat such blocks; review the conflict rather than forcing
an overwrite. Close preferences/config editors during installation.

The registered section policy also proves that a transaction preserves all bytes
outside the owned blocks. It is enforced again at execution, independently of
adapter-generated hashes. Full original file snapshots precede each mutation,
and rollback uses the conservative rules in [safety and recovery](safety-and-restore.md).

The adapter has an internal `plan_uninstall` API that removes only intact owned
blocks and releases their manifest record, preserving even a newly created config
file. It never deletes `default` or deletes the shared file wholesale. This API is
tested; the public `uninstall` command remains reserved for stage 6. Backups are
retained. No automatic restore command is available yet.

## Validation limits

Tests use synthetic ConfigObj fixtures, temporary HOME/XDG roots, fake executable
detection and mocked process launches. They verify parsing, exact preservation,
backups, rollback, per-profile ownership, idempotence and argv handling. They do
not open a real GUI or certify visual rendering across Terminator versions. Actual
font/color rendering and interaction with an existing desktop session still need
manual validation. htop, Vim and VS Code integrations remain future stages.
