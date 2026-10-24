"""Lossless Terminator profiles, section ownership and a shell-free launcher."""

import shutil
from pathlib import Path

from aeronox.adapters.base import DetectionResult, InstallResult, VerificationResult
from aeronox.adapters.terminator_config import (
    PROFILE_NAMES,
    TerminatorConfig,
    profile_block,
    read_managed_sections,
    validate_shared_edit,
)
from aeronox.catalog import PaletteCatalog
from aeronox.paths import XDGPaths
from aeronox.planning import Plan, Planner
from aeronox.storage import ConflictError, FileSnapshot, SafetyError, digest
from aeronox.transactions import TransactionStore


class TerminatorAdapter:
    name = "terminator"

    def __init__(
        self, home: Path | None = None, paths: XDGPaths | None = None,
        *, base_profile: str = "default",
    ):
        self.home = Path.home() if home is None else home
        self.paths = XDGPaths.resolve() if paths is None else paths
        self.config_path = self.paths.config.parent / "terminator/config"
        self.store = TransactionStore(self.home, self.paths, frozenset({self.config_path}),
                                      {self.name: read_managed_sections},
                                      {self.name: validate_shared_edit})
        if not base_profile or base_profile in PROFILE_NAMES.values():
            raise SafetyError("Select a personal base profile, not a generated AeroNox profile")
        self.base_profile = base_profile

    def detect(self) -> DetectionResult:
        executable = shutil.which("terminator")
        if executable is None:
            return DetectionResult(False, False, None, self.config_path,
                                   "not found; skipped (install Terminator separately)")
        real_path = Path(executable).resolve()
        sandboxed = ("snap" in real_path.parts or "flatpak" in str(real_path)
                     or "/snap/" in executable or "/flatpak/" in executable
                     or real_path.name == "snap")
        return DetectionResult(True, not sandboxed, executable, self.config_path,
                               "sandboxed edition; manual setup required" if sandboxed
                               else "available (version not probed)")

    def plan_install(self, palette_catalog: PaletteCatalog) -> Plan:
        planner = self.store.planner()
        source = self.store.files.read(self.config_path)
        document = TerminatorConfig(source.content if source else b"")
        record = planner.manifest.resources.get(str(self.config_path))
        if document.managed_sections() and (record is None or not record.sections):
            raise ConflictError("Unmanaged AeroNox profile name exists; no profiles overwritten")
        base = document.profile(self.base_profile)
        blocks = {PROFILE_NAMES[palette.id]: profile_block(base, palette, document.newline)
                  for palette in palette_catalog.list()}
        content = document.with_profiles(blocks)
        self._plan_shared_write(planner, source, content)
        return planner.build()

    def _plan_shared_write(
        self, planner: Planner, source: FileSnapshot | None, content: bytes,
        *, release: bool = False,
    ) -> None:
        sections = tuple(sorted((name, digest(block))
                                for name, block in read_managed_sections(content).items()))
        planner.write(self.config_path, content, owner=self.name,
                      reason="Remove owned profiles" if release else "Create/update two profiles",
                      shared=True, sections=sections, release=release)
        if planner.changes and planner.changes[-1].expected != source:
            raise ConflictError("Terminator configuration changed while generating the plan")

    def install(self, plan: Plan) -> InstallResult:
        detection = self.detect()
        if not detection.available or not detection.supported:
            raise SafetyError("Terminator is unavailable or unsupported; installation skipped")
        backup_id = self.store.execute(plan)
        return InstallResult(bool(plan.changes), backup_id,
                             "profiles installed" if plan.changes else "already up to date")

    def verify(self) -> VerificationResult:
        try:
            planner = self.store.planner()
            record = planner.manifest.resources.get(str(self.config_path))
            snapshot = self.store.files.read(self.config_path)
            if (record is None or record.owner != self.name or record.ownership != "shared"
                    or snapshot is None or snapshot.mode != record.mode
                    or set(dict(record.sections)) != set(PROFILE_NAMES.values())):
                return VerificationResult(False, "profiles not registered; run install first")
            sections = read_managed_sections(snapshot.content)
            valid = dict(record.sections) == {name: digest(value)
                                              for name, value in sections.items()}
            message = ("profiles verified" if valid
                       else "managed profiles changed; review conflicts before opening")
            return VerificationResult(valid, message)
        except (OSError, SafetyError):
            return VerificationResult(False, "configuration or ownership metadata is unsafe")

    def plan_uninstall(self) -> Plan:
        planner = self.store.planner()
        record = planner.manifest.resources.get(str(self.config_path))
        if record is None:
            return planner.build()
        if (record.owner != self.name or record.ownership != "shared"
                or set(dict(record.sections)) != set(PROFILE_NAMES.values())):
            raise ConflictError("Profile section ownership is missing or incompatible")
        source = self.store.files.read(self.config_path)
        if source is None:
            raise ConflictError("Terminator configuration has been removed")
        document = TerminatorConfig(source.content)
        self._plan_shared_write(planner, source, document.without_managed_profiles(), release=True)
        return planner.build()

    def open_command(self, palette_id: str, args: list[str]) -> list[str]:
        detection = self.detect()
        if not detection.available or not detection.supported or detection.executable is None:
            raise SafetyError("Terminator is unavailable or its edition requires manual setup")
        if palette_id == "original":
            return [detection.executable, *args]
        if palette_id not in PROFILE_NAMES:
            raise SafetyError("Unknown palette for Terminator")
        verification = self.verify()
        if not verification.ok:
            raise ConflictError(verification.message)
        return [detection.executable, "--no-dbus", "--config", str(self.config_path),
                "--profile", PROFILE_NAMES[palette_id], *args]
