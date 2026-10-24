"""Small integration contract using the transaction engine's immutable Plan."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from aeronox.catalog import PaletteCatalog
from aeronox.planning import Plan


@dataclass(frozen=True)
class DetectionResult:
    available: bool
    supported: bool
    executable: str | None
    config_path: Path
    message: str


@dataclass(frozen=True)
class InstallResult:
    changed: bool
    backup_id: str | None
    message: str


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    message: str


class Adapter(Protocol):
    name: str

    def detect(self) -> DetectionResult: ...
    def plan_install(self, palette_catalog: PaletteCatalog) -> Plan: ...
    def install(self, plan: Plan) -> InstallResult: ...
    def verify(self) -> VerificationResult: ...
    def plan_uninstall(self) -> Plan: ...
    def open_command(self, palette_id: str, args: list[str]) -> list[str]: ...
