# AeroNox: assisted VS Code setup

AeroNox generates reference settings, not an installed extension/theme or a
configured profile. `--profile` selects a profile and can create an empty one if
the name is missing. The wrapper therefore checks existing profiles before using
that flag. It never creates profiles or rewrites VS Code settings/registry files.

1. In your chosen native edition, use **Profiles: Create Profile** in the Command
   Palette. Create dedicated profiles named exactly **AeroNox Aviation Red** and
   **AeroNox NVIS Green A**. Copy your personal profile if desired, with independent
   settings. Do not select a mode that shares settings from Default.
2. Select each dedicated profile explicitly in the UI. Choose a suitable built-in
   dark base theme. Open **Preferences: Open User Settings (JSON)** for that
   profile. Confirm you are not editing Default or workspace settings.
3. Inspect `aviation-red.settings.jsonc` or `nvis-green-a.settings.jsonc`, or run
   `aeronox vscode snippet aviation-red`. Manually merge its three top-level
   customization objects into the dedicated profile's settings. Preserve fonts,
   shortcuts and unrelated settings. Do not replace the entire settings file.
4. Merge object keys carefully rather than duplicating them. If you already have
   textMateRules, append the generated rules as the final array entries; the
   conservative readiness check expects that exact suffix. Review array changes.
   Keep the generated semantic-token rules and all 16 terminal ANSI entries.
5. Save and review the result. Run `aeronox vscode status --edition stable` (or
   insiders/codium). Only after the relevant palette reports ready, use:

   ```bash
   aeronox open code --edition stable --palette aviation-red -- /path/to/project
   aeronox open code --edition insiders --palette nvis-green-a --dry-run
   ```

`aeronox install --components vscode --dry-run` previews generation of managed
snippets under XDG data; the real command writes only those AeroNox-owned files.
It does not import them, install an extension, configure a profile or change a
running window. The source examples also ship in assets/vscode and in wheels.
Snippets can be printed without VS Code installed. They contain generated colors
from palettes/*.json; regenerate examples with scripts/generate_vscode_assets.py.

Native defaults are XDG_CONFIG_HOME/Code, Code - Insiders and VSCodium. The read-only
launcher understands current storage.json userDataProfiles entries with relative
profile IDs and independent settings files under User/profiles/<id>/settings.json.
Unknown schemas, duplicate names/locations, symlinks and references to Default
are refused. It never reads User/settings.json (Default). A custom native data
root inside HOME can be selected explicitly with --user-data-dir on status/open.
The launch pins that same directory and uses a new window with the verified name.
Do not pass profile/user-data-directory/reuse-window overrides after --.

Snap, Flatpak and portable editions are detected/reported but require manual
profile configuration and themed launch: no container/portable paths are guessed.
An application wrapper outside the recognized layouts may also need manual use.
Profile storage is internal and may change; unsupported layouts fail closed.
An implicit `aeronox open code` with no active palette prints setup instructions
instead of starting Default. Use native code normally, or explicitly select
`--palette original`, for an unthemed launch. That explicit mode adds no profile.

Readiness is a read-only snapshot, not an atomic guarantee across a concurrently
running application. Avoid changing/deleting profiles during launch. Workspace
settings, language rules, extensions and the base theme can override appearance;
a ready report is not a visual certification. No running-window watcher or
automatic theme switching is included. Manual edits to dedicated profiles remain
user-owned and are never uninstalled or restored by deleting those settings.

Monochromatic ANSI/syntax colors lose conventional red/green categories. Keep
text/icons and native diagnostics for critical signals. These palettes are merely
inspired by aviation lighting, not NVIS certified, and claim no medical benefit.

References: [VS Code profiles](https://code.visualstudio.com/docs/configure/profiles)
and [theme customizations](https://code.visualstudio.com/docs/configure/themes).
These links are optional documentation; AeroNox performs no runtime network requests.
