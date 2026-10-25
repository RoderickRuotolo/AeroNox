# Application integrations

## Terminator (stage 3)

The native Terminator executable must already be on PATH. AeroNox never installs
it. Missing applications are skipped with an actionable message; VS Code
uses assisted/manual setup in this release. Recognized Snap/Flatpak executable paths are
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
watchers are created. `apply` persists the palette for new wrapper launches; `restore` returns mode to original.

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
tested and used by public `uninstall` in a combined transaction. Backups are
retained. `restore` changes only active mode; it never bulk-restores config backups.

## Validation limits

Tests use synthetic ConfigObj fixtures, temporary HOME/XDG roots, fake executable
detection and mocked process launches. They verify parsing, exact preservation,
backups, rollback, per-profile ownership, idempotence and argv handling. They do
not open a real GUI or certify visual rendering across Terminator versions. Actual
font/color rendering and interaction with an existing desktop session still need
manual validation. VS Code uses the separate assisted workflow described below.

## htop (stage 4)

```bash
aeronox install --components htop --dry-run
aeronox install --components htop
aeronox open htop --palette aviation-red
aeronox open htop --palette nvis-green-a --dry-run
aeronox open htop --palette aviation-red -- --filter 'text with spaces'
```

The native htop executable must be on PATH; recognized sandboxed editions are
skipped. Source precedence is an explicit nonempty HTOPRC, the XDG htoprc, then
legacy `~/.htoprc`. Sources must be absolute, inside HOME and pass the filesystem
safety checks. Missing sources produce a minimal config with `color_scheme=1`;
system-wide preferences are not imported. Legacy files are copied without moving,
rewriting or deleting them. Unset HTOPRC before installation if it points at a
managed copy rather than a personal source.

Generated files live at `$XDG_DATA_HOME/aeronox/htop/<palette>/htoprc`. Original
bytes, columns, meters, sorting, unknown settings and comments are preserved in
the copies except the color_scheme value. Duplicate color_scheme settings, NUL
and CR-only line endings are refused. LF/CRLF are supported. The two copies use
the same native monochrome setting; they do not contain independent RGB palettes.

The themed launcher uses `-C` and sets HTOPRC only for the child. Newer htop history
is redirected using a per-palette XDG_STATE_HOME under AeroNox state; the parent's
environment is unchanged. Dry-run outputs JSON with argv and only the environment
delta, never the whole process environment. Original mode inherits the normal
command/environment without overriding HTOPRC. Native config/history semantics
are described in the [htop manual](https://github.com/htop-dev/htop/blob/main/htop.1.in).

Monochrome relies on the parent terminal's appearance; use a coordinated Terminator
profile for a red/green environment. htop does not promise element-by-element RGB
matching. Native PTY smoke tests check Help/Setup/Quit labels for both selected
copies; actual desktop rendering and readability under both Terminator profiles
still need manual visual validation.

htop may reformat/rewrite the managed copy when it exits. Hash/mode mismatches are
reported on subsequent managed launch, installation and removal; edited bytes are
preserved. There is no automatic reconciliation/adoption command in this stage.
Do not remove ownership records to suppress a conflict; retain the changed copy
for review. Normal htop use outside the wrapper is still available. Installation
snapshots protect previous generated versions; the original personal htoprc is
never a mutation target. Runtime histories are not pruned or removed automatically.

## Vim (stage 4)

```bash
aeronox install --components vim --dry-run
aeronox install --components vim
aeronox open vim --palette aviation-red -- README.md
aeronox open vim --palette nvis-green-a --dry-run
# To pass Vim's own -- for filenames beginning with '-' or '+':
aeronox open vim --palette aviation-red -- -- '-example.txt'
```

The native Vim executable must be on PATH. Neovim and other editors are not added
implicitly; recognized sandboxed packages are skipped. Files are generated under
`$XDG_DATA_HOME/aeronox/vim/colors/aeronox_red.vim` and `aeronox_green.vim`.
No `.vimrc`, `.vim` directory or shell startup file is created or modified.
Each theme includes Normal, Comment, Constant, String, Identifier, Statement,
PreProc, Type, Special, LineNr, CursorLine, Visual, StatusLine, Search, ErrorMsg,
WarningMsg, DiffAdd, DiffDelete and Cursor. Semantic RGB values come exclusively
from the central palette JSON. cterm values are nearest sRGB approximations among
the stable xterm cube/grayscale indices 16–255; configurable ANSI indices 0–15 are
avoided. Terminals with fewer colors may not reproduce this fallback accurately.

Error/warning/diff groups include bold, reverse or underline differences, so hue
is not the only cue. Terminal capability, font support and the user's settings
still determine appearance. The generated scheme provides GUI/True Color values
but does not turn termguicolors on automatically. See the official
[Vim colors guide](https://vimhelp.org/usr_06.txt.html) and
[terminal documentation](https://vimhelp.org/term.txt.html).

The wrapper prepends the XDG runtime directory through a safely quoted runtimepath
value and executes `colorscheme aeronox_red` or `aeronox_green` using a separate
`-c` argument. Spaces, commas, quotes, backslashes and bars are tested with real
headless Vim; control characters in runtime paths are refused. Arguments after
`--` pass unchanged. Personal startup settings still load in real launches and
plugins can override highlights later. Installation never executes Vim or sources
vimrc. Original mode starts Vim normally without changing runtimepath.

Headless tests use temporary HOME/XDG and `vim -Nu NONE -i NONE -n -es`, exercising
both palettes in True Color and notermguicolors modes. Tests verify colors_name,
Normal RGB/cterm attributes and non-color ErrorMsg emphasis. Native executables
are optional for the smoke tests; missing ones are reported as skips. Core
resource/ownership tests always run. No test uses personal Vim configurations.

## Combined installation and removal scope

`aeronox install --components terminator,htop,vim` installs available components in
that order, each with its own backup/transaction. It never installs the applications
themselves. A later failure reports earlier committed components and backup IDs;
it is not a single atomic transaction across every application. Re-running an
unchanged install does not duplicate resources or create more backups.

The htop/Vim internal removal plans delete only intact owned resources; modified
or unregistered files are preserved. Public `uninstall` aborts the complete removal
if any resource conflicts; `restore` can independently return active mode to original.
Explicit --palette remains per launch only, while `apply` changes the persisted mode.

## VS Code assisted (stage 5)

Use `aeronox vscode guide` or the [packaged setup guide](../assets/vscode/GUIDE.md).
`install --components vscode` writes only reference snippets; it does not create
profiles, install themes/extensions or change Default. Manually create the two
named profiles, merge settings and check `aeronox vscode status` before themed use.
`aeronox open code --edition stable --palette aviation-red -- /path/to/project`
then opens the verified existing profile in a new window. Missing profiles cause
instructions rather than implicit creation through --profile. Snap/Flatpak/portable
layouts remain manual. Detailed [read-only checks and limits](vscode.md) include
edition roots, JSONC, overrides and concurrency. Desktop visual validation and
running-window synchronization are outside these automated tests.

## Shared mode lifecycle (stage 6)

`aeronox apply aviation-red` or `apply nvis-green-a` changes only the mode used by
later implicit wrapper launches. It does not edit colors, start apps or recolor
open windows. `current` prints the mode, and missing state means original.
`restore` returns to original without removing profiles/resources or touching
personal configs. All mutations accept --dry-run and no-ops do not create backups.

`uninstall` removes only intact known resources and resets mode in one transaction;
any conflict aborts the entire removal. It also works when app executables are
absent. Unknown/outdated manifest destinations are preserved for review. Backups,
history and manually configured VS Code profiles remain. Original Code opening is
still explicit via --palette original/native code, preserving the assisted setup
boundary when implicit opening has no active palette.
