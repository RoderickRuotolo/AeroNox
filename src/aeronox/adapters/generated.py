"""Common ownership checks for integrations using separate generated files."""

import shutil
from pathlib import Path

from aeronox.adapters.base import DetectionResult, InstallResult, VerificationResult
from aeronox.models import PALETTE_IDS
from aeronox.paths import XDGPaths
from aeronox.planning import Plan
from aeronox.storage import ConflictError, SafetyError
from aeronox.transactions import TransactionStore


def detect_native(name: str, config_path: Path) -> DetectionResult:
    executable = shutil.which(name)
    if executable is None:
        return DetectionResult(False, False, None, config_path,
                               f"not found; skipped (install {name} separately)")
    real = Path(executable).resolve()
    sandboxed = ("snap" in real.parts or "flatpak" in str(real) or real.name == "snap"
                 or "/snap/" in executable or "/flatpak/" in executable)
    return DetectionResult(True, not sandboxed, executable, config_path,
                           "sandboxed edition; manual setup required" if sandboxed
                           else "available (version not probed)")


class GeneratedAdapter:
    """Never adopt unregistered files or remove externally modified resources."""

    name: str
    config_path: Path

    def __init__(self, home: Path, paths: XDGPaths, targets: dict[str, Path]):
        self.home = home
        self.paths = paths
        self.targets = targets
        self.store = TransactionStore(home, paths, frozenset(targets.values()))

    def detect(self) -> DetectionResult:
        return detect_native(self.name, self.config_path)

    def install(self, plan: Plan) -> InstallResult:
        self.executable()
        backup_id = self.store.execute(plan)
        return InstallResult(bool(plan.changes), backup_id,
                             "resources installed" if plan.changes else "already up to date")

    def executable(self) -> str:
        detection = self.detect()
        if not detection.supported or detection.executable is None:
            raise SafetyError(f"{self.name} is unavailable or requires manual setup")
        return detection.executable

    def require_palette(self, palette_id: str) -> Path:
        if palette_id not in PALETTE_IDS:
            raise SafetyError(f"Unknown palette for {self.name}")
        path = self.targets[palette_id]
        record = self.store.planner().manifest.resources.get(str(path))
        snapshot = self.store.files.read(path)
        if record is None or snapshot is None:
            raise ConflictError(
                f"{self.name}: integration not ready; run install --components {self.name}"
            )
        if (record.owner != self.name or record.ownership != "generated" or record.sections
                or snapshot.sha256 != record.sha256 or snapshot.mode != record.mode):
            raise ConflictError(
                f"{self.name}: managed resource changed; review conflicts before use"
            )
        return path

    def verify(self) -> VerificationResult:
        try:
            for palette_id in self.targets:
                self.require_palette(palette_id)
        except (OSError, SafetyError):
            return VerificationResult(False, f"{self.name} resources missing, modified or unsafe")
        return VerificationResult(True, f"{self.name} resources verified")

    def plan_uninstall(self) -> Plan:
        planner = self.store.planner()
        for path in self.targets.values():
            if str(path) in planner.manifest.resources:
                planner.remove(path, owner=self.name, reason="Remove intact generated resource")
        return planner.build()
