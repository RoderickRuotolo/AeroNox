"""Private transaction snapshots and recovery journals, never configuration logs."""

import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path

from aeronox.planning import PlannedChange
from aeronox.storage import FileSnapshot, SafeFiles, SafetyError, decode_json, digest

BACKUP_ID = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{16}")
STATUSES = {"prepared", "committed", "rolled_back", "recovery_required"}


class BackupStore:
    def __init__(self, files: SafeFiles, state_directory: Path):
        files.validate(state_directory / "state.json")
        self.files = files
        self.state_directory = state_directory
        self.root = state_directory / "backups"

    def directory(self, backup_id: str) -> Path:
        if BACKUP_ID.fullmatch(backup_id) is None:
            raise SafetyError("Invalid backup ID")
        return self.root / backup_id

    def prepare(self, changes: tuple[PlannedChange, ...]) -> str:
        self.files.private_directory(self.state_directory, create=True)
        self.files.private_directory(self.root, create=True)
        backup_id = (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
                     + "-" + secrets.token_hex(8))
        directory = self.directory(backup_id)
        self.files.private_directory(directory, create=True)
        entries = []
        for index, item in enumerate(changes):
            before = item.expected
            if before is not None:
                self.files.replace(directory / f"{index}.bin", before.content, None)
            entries.append({
                "path": str(item.path), "action": item.action,
                "before": before.metadata() if before else None,
                "blob": f"{index}.bin" if before else None,
                "after": {"sha256": digest(item.content), "size": len(item.content),
                          "mode": item.mode} if item.content is not None else None,
            })
        journal = {"schema_version": 1, "id": backup_id, "status": "prepared",
                   "entries": entries, "conflicts": []}
        self._save(backup_id, journal, None)
        return backup_id

    def _save(
        self, backup_id: str, journal: dict[str, object], expected: FileSnapshot | None,
    ) -> None:
        content = (json.dumps(journal, indent=2, sort_keys=True) + "\n").encode()
        self.files.replace(self.directory(backup_id) / "journal.json", content, expected)

    def inspect(self, backup_id: str) -> dict[str, object]:
        directory = self.directory(backup_id)
        for path in (self.state_directory, self.root, directory):
            self.files.private_directory(path)
        snapshot = self.files.read(directory / "journal.json")
        if snapshot is None or snapshot.mode != 0o600:
            raise SafetyError("Missing or insecure backup journal")
        try:
            journal = decode_json(snapshot.content)
            if (not isinstance(journal, dict) or type(journal.get("schema_version")) is not int
                    or journal.get("schema_version") != 1
                    or journal.get("id") != backup_id or journal.get("status") not in STATUSES
                    or not isinstance(journal.get("entries"), list)
                    or not isinstance(journal.get("conflicts"), list)):
                raise ValueError
            for index, entry in enumerate(journal["entries"]):
                if (not isinstance(entry, dict)
                        or set(entry) != {"path", "action", "before", "blob", "after"}
                        or not isinstance(entry["path"], str)
                        or entry["action"] not in {"create", "update", "remove"}):
                    raise ValueError
                self.files.validate(Path(entry["path"]))
                after = entry["after"]
                if after is not None and (
                    not isinstance(after, dict) or set(after) != {"sha256", "size", "mode"}
                    or not isinstance(after["sha256"], str)
                    or re.fullmatch(r"[0-9a-f]{64}", after["sha256"]) is None
                    or type(after["size"]) is not int or after["size"] < 0
                    or type(after["mode"]) is not int or not 0 <= after["mode"] <= 0o777
                ):
                    raise ValueError
                before = entry["before"]
                if before is None:
                    if entry["blob"] is not None:
                        raise ValueError
                elif (entry["blob"] != f"{index}.bin" or not isinstance(before, dict)
                      or set(before) != {"sha256", "size", "mode", "uid", "gid", "mtime_ns"}
                      or not isinstance(before["sha256"], str)
                      or re.fullmatch(r"[0-9a-f]{64}", before["sha256"]) is None
                      or any(type(before[key]) is not int or before[key] < 0
                             for key in ("size", "mode", "uid", "gid"))
                      or before["mode"] > 0o777 or type(before["mtime_ns"]) is not int):
                    raise ValueError
            return journal
        except (ValueError, TypeError, KeyError) as exc:
            raise SafetyError("Invalid backup journal") from exc

    def mark(self, backup_id: str, status: str, conflicts: tuple[str, ...] = ()) -> None:
        if status not in STATUSES:
            raise SafetyError("Invalid transaction status")
        path = self.directory(backup_id) / "journal.json"
        before = self.files.read(path)
        journal = self.inspect(backup_id)
        journal["status"] = status
        journal["conflicts"] = list(conflicts)
        self._save(backup_id, journal, before)

    def list(self) -> tuple[dict[str, object], ...]:
        try:
            self.files.private_directory(self.state_directory)
        except SafetyError as exc:
            if isinstance(exc.__cause__, FileNotFoundError):
                return ()
            raise
        names = self.files.names(self.root)
        try:
            self.files.private_directory(self.root)
        except SafetyError as exc:
            if isinstance(exc.__cause__, FileNotFoundError):
                return ()
            raise
        return tuple(self.inspect(name) for name in names if BACKUP_ID.fullmatch(name))

    def read_blob(self, backup_id: str, index: int) -> bytes | None:
        journal = self.inspect(backup_id)
        if type(index) is not int or not 0 <= index < len(journal["entries"]):
            raise SafetyError("Invalid backup entry index")
        entry = journal["entries"][index]
        if entry["before"] is None:
            return None
        snapshot = self.files.read(self.directory(backup_id) / entry["blob"])
        if (snapshot is None or snapshot.mode != 0o600
                or snapshot.sha256 != entry["before"]["sha256"]
                or len(snapshot.content) != entry["before"]["size"]):
            raise SafetyError("Backup is missing, insecure or has a checksum mismatch")
        return snapshot.content
