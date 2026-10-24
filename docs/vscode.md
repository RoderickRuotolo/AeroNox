# VS Code assisted integration (stage 5)

Start with the packaged [manual setup guide](../assets/vscode/GUIDE.md), also
available offline with `aeronox vscode guide`. The generated examples are
[aviation-red.settings.jsonc](../assets/vscode/aviation-red.settings.jsonc) and
[nvis-green-a.settings.jsonc](../assets/vscode/nvis-green-a.settings.jsonc).

## What installation means

`aeronox install --components vscode` generates two owned reference snippets under
`$XDG_DATA_HOME/aeronox/vscode/`. It does not import settings, install a theme
extension, create a profile or recolor open windows. Missing editors are skipped;
`aeronox vscode snippet <palette>` and the packaged examples remain available
without an editor. The JSONC objects cover workbench colors, TextMate rules,
semantic-token rules and all 16 terminal ANSI colors. The palette JSON files are
the only hand-maintained colors. `scripts/generate_vscode_assets.py` regenerates
examples; `--check` refuses stale examples without writing them.

A user manually merges these objects into existing dedicated profiles, preserving
unrelated preferences. The full settings file must never be replaced blindly.
Generated TextMate rules must be the final array entries for the conservative
readiness check. Colors/styles must match the generated reference values; alternate
spellings, scope ordering or equivalent custom rules may require manual use.
Workbench/syntax coverage is intentionally partial; a built-in dark base theme,
workspace settings and extensions still affect uncustomized elements.

## Edition detection

| Selection | Executable | Native data root |
| --- | --- | --- |
| stable | code | XDG_CONFIG_HOME/Code |
| insiders | code-insiders | XDG_CONFIG_HOME/Code - Insiders |
| codium | codium | XDG_CONFIG_HOME/VSCodium |
| flatpak | com.visualstudio.code | Not assumed |
| codium-flatpak | com.vscodium.codium | Not assumed |

`auto` prefers an available native Stable, then Insiders, then VSCodium, before
packaged alternatives. Snap executable paths/snap wrappers, exported Flatpak
launchers and recognized portable layouts are reported separately. A portable
environment variable or known portable installation marker disables themed launch.
No processes or version probes are run during detection or dry-run. Arbitrary
launcher scripts, remote/server editions and unrecognized packaging cannot be
fully classified and are not certified as supported.

Packaged editions can receive reference snippets but require manual profile
setup/launch. No container path is guessed or written. Native custom data roots
may be selected explicitly using `--user-data-dir` on `vscode status`/`open code`;
they must be absolute and inside HOME and pass the existing safety checks.

## Read-only readiness and launch

VS Code's documented CLI behavior creates a new empty profile when an unknown
name is passed to `--profile`; see the [official profile documentation](https://code.visualstudio.com/docs/configure/profiles).
The AeroNox wrapper therefore refuses a themed launch until it can verify the
requested existing profile and its manually merged customization values.

The current native layout is read from `User/globalStorage/storage.json`, using
`userDataProfiles` name/location entries and independent settings at
`User/profiles/<relative-id>/settings.json`. The mapping is based on the upstream
[profile storage service](https://github.com/microsoft/vscode/blob/main/src/vs/platform/userDataProfile/node/userDataProfile.ts).
It is internal metadata and may change. Unknown/legacy location schemas are refused.
Only the two exact AeroNox names are considered. Duplicate names/locations,
transient/default profiles, traversal/URI locations and settings inherited from
Default are rejected. Default's `User/settings.json` is never read or written.

The JSONC reader accepts comments, trailing commas and UTF-8 BOM, preserving string
content. Duplicate keys, invalid/non-finite values and malformed JSONC are refused.
No serialization is applied to user files. Errors redact source contents and
profile IDs; `vscode status --paths` is the explicit option for local root/snippet
paths. `doctor` now reports edition availability and selected-profile readiness
without printing personal metadata or paths by default.

Before returning argv, registry/settings fingerprints are rechecked. The launch
pins the verified `--user-data-dir`, selects the existing name and requests a new
window. Conflicting passthrough profile/data-root/reuse-window flags are refused.
Other arguments remain individual argv entries without shell concatenation.
An implicit `open code` in initial original mode prints setup instructions instead
of starting Default. Explicit `--palette original` delegates normally without a
profile flag; it is an intentional ordinary application launch.

This is optimistic verification, not a VS Code transaction: a profile could be
changed/deleted between the final check and CLI handling. Close profile editors
while launching. Required values being present does not prove final rendered
appearance: workspace/language overrides and extensions can still change it.
No GUI integration tests, extension installation or running-window synchronization
are included in this stage. Upstream theme settings are described in the
[official theme documentation](https://code.visualstudio.com/docs/configure/themes).

## Ownership and validation

Only the two generated reference files belong to the AeroNox manifest. Installation
is idempotent; conflicting snippet edits are preserved. Private backups and
rollback use the existing transaction engine. Internal removal planning removes
only intact snippets; manually created VS Code profiles/settings remain user-owned.

Tests use synthetic registries and JSONC settings in temporary HOME/XDG roots,
including private placeholder values, symlinks and concurrent edits. Actual Code
GUI processes are never invoked. A fake executable checks installed-wheel CLI
behavior without creating profiles. Asset drift checks ensure packaged examples
match generation from central palettes. Manual visual validation remains pending.
