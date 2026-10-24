"""Read-only plans and strict versioned ownership records."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from aeronox.models import PALETTE_IDS
from aeronox.storage import ConflictError, FileSnapshot, SafeFiles, SafetyError, decode_json, digest

Action = Literal["create", "update", "remove"]
Ownership = Literal["generated", "shared"]
HASH = re.compile(r"[0-9a-f]{64}")
OWNER = re.compile(r"[a-z][a-z0-9-]{0,31}")


@dataclass(frozen=True)
class Resource:
    sha256: str
    mode: int
    owner: str
    ownership: Ownership

    def to_dict(self) -> dict[str, object]:
        return {"sha256": self.sha256, "mode": self.mode,
                "owner": self.owner, "ownership": self.ownership}


@dataclass(frozen=True)
class Manifest:
    mode: str
    resources: MappingProxyType[str, Resource]

    @classmethod
    def empty(cls) -> "Manifest":
        return cls("original", MappingProxyType({}))

    @classmethod
    def load(cls, snapshot: FileSnapshot | None, files: SafeFiles) -> "Manifest":
        if snapshot is None:
            return cls.empty()
        if snapshot.mode != 0o600:
            raise SafetyError("state.json must have mode 0600")
        try:
            data = decode_json(snapshot.content)
            if (not isinstance(data, dict)
                    or set(data) != {"schema_version", "mode", "resources"}
                    or type(data["schema_version"]) is not int or data["schema_version"] != 1
                    or data["mode"] not in ("original", *PALETTE_IDS)
                    or not isinstance(data["resources"], dict)):
                raise ValueError
            resources = {}
            for name, entry in data["resources"].items():
                files.validate(Path(name))
                if (not isinstance(entry, dict)
                        or set(entry) != {"sha256", "mode", "owner", "ownership"}
                        or not isinstance(entry["sha256"], str)
                        or HASH.fullmatch(entry["sha256"]) is None
                        or type(entry["mode"]) is not int or not 0 <= entry["mode"] <= 0o777
                        or not isinstance(entry["owner"], str)
                        or OWNER.fullmatch(entry["owner"]) is None
                        or entry["ownership"] not in ("generated", "shared")):
                    raise ValueError
                resources[name] = Resource(**entry)
            return cls(data["mode"], MappingProxyType(resources))
        except (ValueError, TypeError, KeyError) as exc:
            raise SafetyError("Invalid state manifest; refusing to overwrite it") from exc

    def serialize(self) -> bytes:
        data = {"schema_version": 1, "mode": self.mode,
                "resources": {name: item.to_dict() for name, item in self.resources.items()}}
        return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()


@dataclass(frozen=True)
class PlannedChange:
    path: Path
    action: Action
    expected: FileSnapshot | None
    content: bytes | None
    mode: int
    owner: str
    ownership: Ownership
    reason: str
    conflict_rule: str = "abort if the source or ownership record has changed"

    def describe(self) -> str:
        old_size = len(self.expected.content) if self.expected else 0
        new_size = len(self.content) if self.content is not None else 0
        # Never include config contents or an untrusted reason in CLI output.
        return (f"{self.action}: {self.path} ({old_size} -> {new_size} bytes; "
                f"{self.ownership}, {self.owner}; {self.conflict_rule})")


@dataclass(frozen=True)
class Plan:
    changes: tuple[PlannedChange, ...]
    manifest_before: FileSnapshot | None
    manifest: Manifest

    def describe(self) -> str:
        return "\n".join(item.describe() for item in self.changes) or "No file changes planned."


class Planner:
    """Exact whitelist of adapter-approved targets; planning never creates files.

    Explicit shared-file enrollment is reserved for future adapters that preserve
    personal sections. Shared files can never be removed by the generic engine.
    """

    def __init__(self, files: SafeFiles, state: Path, allowed: frozenset[Path]):
        self.files = files
        self.state = state
        files.validate(state)
        self.allowed = allowed
        self.before = files.read(state)
        if self.before is not None:
            files.private_directory(state.parent)
        self.manifest = Manifest.load(self.before, files)
        self.changes: list[PlannedChange] = []

    def _check_target(self, path: Path) -> None:
        self.files.validate(path)
        if path not in self.allowed or path == self.state or path.is_relative_to(self.state.parent):
            raise SafetyError("Target is not an authorized adapter resource")
        if path.name in {".vimrc", ".bashrc", ".zshrc", "settings.json"}:
            raise SafetyError("Personal startup files and VS Code settings are protected")
        if any(item.path == path for item in self.changes):
            raise SafetyError("A plan cannot change the same target twice")

    def write(
        self, path: Path, content: bytes, *, owner: str, reason: str,
        shared: bool = False, mode: int = 0o600,
    ) -> None:
        self._check_target(path)
        if not isinstance(content, bytes) or len(content) > 16 * 1024 * 1024:
            raise SafetyError("Planned content must be bytes, at most 16 MiB")
        if OWNER.fullmatch(owner) is None or type(mode) is not int or not 0 <= mode <= 0o777:
            raise SafetyError("Invalid resource owner or mode")
        before = self.files.read(path)
        record = self.manifest.resources.get(str(path))
        ownership: Ownership = "shared" if shared else "generated"
        if record is not None:
            if record.owner != owner or record.ownership != ownership:
                raise ConflictError("Resource ownership differs from the requested operation")
            if before is None or before.sha256 != record.sha256 or before.mode != record.mode:
                raise ConflictError(f"Managed resource was modified or removed: {path}")
        elif before is not None and not shared:
            raise ConflictError(f"An unmanaged resource already exists: {path}")
        if shared and before is None and record is None:
            raise SafetyError("Shared enrollment requires an existing personal file")
        permissions = before.mode if before is not None else mode
        if before is not None and before.content == content and record is not None:
            return
        self.changes.append(PlannedChange(
            path, "create" if before is None else "update", before, content, permissions,
            owner, ownership, reason,
        ))

    def remove(self, path: Path, *, owner: str, reason: str) -> None:
        self._check_target(path)
        record = self.manifest.resources.get(str(path))
        before = self.files.read(path)
        if record is None or record.owner != owner or record.ownership != "generated":
            raise ConflictError("Only intact, generated AeroNox resources may be removed")
        if before is None or before.sha256 != record.sha256 or before.mode != record.mode:
            raise ConflictError(f"Managed resource was modified or removed: {path}")
        self.changes.append(PlannedChange(
            path, "remove", before, None, before.mode, owner, "generated", reason,
        ))

    def build(self) -> Plan:
        resources = dict(self.manifest.resources)
        for item in self.changes:
            if item.action == "remove":
                del resources[str(item.path)]
            else:
                assert item.content is not None
                resources[str(item.path)] = Resource(
                    digest(item.content), item.mode, item.owner, item.ownership,
                )
        return Plan(tuple(self.changes), self.before,
                    Manifest(self.manifest.mode, MappingProxyType(resources)))
