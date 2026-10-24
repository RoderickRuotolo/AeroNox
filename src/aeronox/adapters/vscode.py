"""Assisted VS Code snippets and read-only checks before selecting existing profiles."""

import os
import re
import shutil
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from aeronox.adapters.base import DetectionResult, InstallResult
from aeronox.adapters.generated import GeneratedAdapter
from aeronox.adapters.vscode_theme import PROFILE_NAMES, contains_settings, snippet, theme_settings
from aeronox.catalog import PaletteCatalog
from aeronox.jsonc import parse_jsonc
from aeronox.paths import XDGPaths
from aeronox.planning import Plan
from aeronox.storage import ConflictError, FileSnapshot, SafetyError

# Native editions have distinct data directories. Packaged editions are detected
# but not mapped to guessed container paths or launched with a theme automatically.
EDITIONS = {
    "stable": ("code", "Code", "native"),
    "insiders": ("code-insiders", "Code - Insiders", "native"),
    "codium": ("codium", "VSCodium", "native"),
    "flatpak": ("com.visualstudio.code", "Code", "flatpak"),
    "codium-flatpak": ("com.vscodium.codium", "VSCodium", "flatpak"),
}
EDITION_CHOICES = ("auto", *EDITIONS)
PROFILE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")


@dataclass(frozen=True)
class Installation:
    edition: str
    executable: str | None
    data_root: Path
    kind: str


def installations(home: Path, paths: XDGPaths) -> tuple[Installation, ...]:
    result = []
    for edition, (command, directory, packaging) in EDITIONS.items():
        executable = shutil.which(command)
        kind = packaging
        if executable:
            real = Path(executable).resolve()
            if "/snap/" in executable or "snap" in real.parts or real.name == "snap":
                kind = "snap"
            elif "/flatpak/" in executable or "flatpak" in str(real):
                kind = "flatpak"
            elif packaging == "native" and (
                os.environ.get("VSCODE_PORTABLE")
                or ((real.parent.parent / "resources/app/product.json").is_file()
                    and (real.parent.parent / "data").is_dir())
            ):
                kind = "portable"
        result.append(Installation(edition, executable, paths.config.parent / directory, kind))
    return tuple(result)


def guide() -> str:
    return files("aeronox.vscode_assets").joinpath("GUIDE.md").read_text(encoding="utf-8")


class VSCodeAdapter(GeneratedAdapter):
    name = "vscode"

    def __init__(
        self, home: Path | None = None, paths: XDGPaths | None = None, *, edition: str = "auto",
        user_data_dir: Path | None = None,
    ):
        home = Path.home() if home is None else home
        paths = XDGPaths.resolve() if paths is None else paths
        if edition not in EDITION_CHOICES:
            raise SafetyError("Unknown VS Code edition")
        self.edition = edition
        self.user_data_dir = user_data_dir
        self.config_path = paths.config.parent / "Code"
        targets = {palette: paths.data / "vscode" / f"{palette}.settings.jsonc"
                   for palette in PROFILE_NAMES}
        super().__init__(home, paths, targets)
        if user_data_dir is not None:
            self.store.files.validate(user_data_dir / "User/globalStorage/storage.json")

    def selected(self) -> Installation:
        detected = installations(self.home, self.paths)
        if self.edition != "auto":
            selected = next(item for item in detected if item.edition == self.edition)
        else:
            available = [item for item in detected if item.executable]
            selected = next((item for item in available if item.kind == "native"),
                            available[0] if available else detected[0])
        if self.user_data_dir is not None:
            selected = Installation(selected.edition, selected.executable,
                                    self.user_data_dir, selected.kind)
        return selected

    def detect(self) -> DetectionResult:
        selected = self.selected()
        available = selected.executable is not None
        message = (
            f"{selected.edition}/{selected.kind}; snippets only; manual profile setup required"
            if available else "not found; skipped (snippets available via vscode snippet)"
        )
        # Snippet generation is safe even for detected packaged editions; this does
        # not mean their profile layout is supported by the themed launcher.
        return DetectionResult(available, available, selected.executable,
                               selected.data_root, message)

    def plan_install(self, palette_catalog: PaletteCatalog) -> Plan:
        planner = self.store.planner()
        for palette in palette_catalog.list():
            planner.write(self.targets[palette.id], snippet(palette), owner=self.name,
                          reason="Generate reference snippet for manual dedicated-profile setup")
        return planner.build()

    def install(self, plan: Plan) -> InstallResult:
        self.executable()
        backup_id = self.store.execute(plan)
        message = ("snippets generated; manual profile setup required" if plan.changes
                   else "snippets up to date; manual profile setup still required")
        return InstallResult(bool(plan.changes), backup_id, message)

    def _read(self, path: Path) -> FileSnapshot | None:
        try:
            return self.store.files.read(path)
        except (OSError, SafetyError) as exc:
            message = "VS Code metadata/settings cannot be read safely (details redacted)"
            raise SafetyError(message) from exc

    def prepared_profile(self, palette_id: str, selected: Installation | None = None) -> str:
        if palette_id not in PROFILE_NAMES:
            raise SafetyError("Unknown VS Code palette")
        selected = self.selected() if selected is None else selected
        if selected.executable is None:
            raise SafetyError("VS Code edition not available; install the application separately")
        if selected.kind != "native":
            raise SafetyError("Packaged/portable VS Code profile layout requires manual launch")
        registry_path = selected.data_root / "User/globalStorage/storage.json"
        registry = self._read(registry_path)
        if registry is None:
            raise SafetyError(
                "Dedicated profile not found; create it manually (aeronox vscode guide)"
            )
        data = parse_jsonc(registry.content)
        entries = data.get("userDataProfiles", []) if isinstance(data, dict) else None
        if not isinstance(entries, list):
            raise SafetyError("Unsupported VS Code profile registry format; configure manually")
        name = PROFILE_NAMES[palette_id]
        matches = [entry for entry in entries
                   if isinstance(entry, dict) and entry.get("name") == name]
        if len(matches) != 1:
            raise SafetyError("Dedicated profile missing or ambiguous; create/review it manually")
        entry = matches[0]
        location = entry.get("location")
        if (not isinstance(location, str) or PROFILE_ID.fullmatch(location) is None
                or location.lower() in {"default", "builtin"} or entry.get("isDefault", False)
                or entry.get("isTransient", False)):
            raise SafetyError("Unsupported dedicated profile location; Default is never selected")
        aliases = sum(isinstance(item, dict) and item.get("location") == location
                      for item in entries)
        if aliases != 1:
            raise SafetyError("Ambiguous shared profile location; configure manually")
        flags = entry.get("useDefaultFlags", {})
        if not isinstance(flags, dict) or flags.get("settings", False) is not False:
            raise SafetyError(
                "Dedicated profile must have independent settings, not Default settings"
            )
        settings_path = selected.data_root / "User/profiles" / location / "settings.json"
        settings = self._read(settings_path)
        if settings is None:
            raise SafetyError("Dedicated settings missing; merge the snippet manually")
        expected = theme_settings(PaletteCatalog().get(palette_id))
        if not contains_settings(parse_jsonc(settings.content), expected):
            raise SafetyError(
                "Profile colors are not prepared; merge the matching snippet manually"
            )
        if self._read(registry_path) != registry or self._read(settings_path) != settings:
            raise ConflictError("VS Code profile changed during verification; retry after review")
        return name

    def profile_status(self, palette_id: str) -> str:
        try:
            self.prepared_profile(palette_id)
        except SafetyError as exc:
            return f"manual setup pending ({exc})"
        return "ready (read-only snapshot; workspace/extensions may override appearance)"

    def open_command(self, palette_id: str, args: list[str]) -> list[str]:
        selected = self.selected()
        if selected.executable is None:
            raise SafetyError("VS Code edition not available")
        forbidden = ("--profile", "--user-data-dir", "--profile-temp", "--reuse-window")
        if any(arg == "-r" or any(arg == option or arg.startswith(option + "=")
                                 for option in forbidden) for arg in args):
            raise SafetyError(
                "Profile/data-directory/window overrides must not bypass profile checks"
            )
        if palette_id == "original":
            if self.user_data_dir is not None:
                raise SafetyError(
                    "Use native code for an original launch with a custom data directory"
                )
            return [selected.executable, *args]
        name = self.prepared_profile(palette_id, selected)
        return [selected.executable, "--user-data-dir", str(selected.data_root),
                "--new-window", "--profile", name, *args]
