"""Snapshot-first transactions with conservative rollback and a private writer lock."""

import fcntl
import os
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from aeronox.backups import BackupStore
from aeronox.paths import XDGPaths
from aeronox.planning import Plan, PlannedChange, Planner, SectionReader, SharedValidator
from aeronox.storage import ConflictError, FileSnapshot, SafeFiles, SafetyError


class TransactionError(SafetyError):
    def __init__(self, backup_id: str, conflicts: tuple[str, ...]):
        self.backup_id = backup_id
        self.conflicts = conflicts
        result = "manual recovery required" if conflicts else "file changes rolled back"
        super().__init__(f"Transaction failed; {result}. Backup: {backup_id}")


class TransactionStore:
    def __init__(
        self, home: Path, paths: XDGPaths, allowed: frozenset[Path],
        section_readers: Mapping[str, SectionReader] | None = None,
        shared_validators: Mapping[str, SharedValidator] | None = None,
    ):
        self.files = SafeFiles(home)
        self.paths = paths
        self.state = paths.state / "state.json"
        self.allowed = allowed
        self.section_readers = dict(section_readers or {})
        self.shared_validators = dict(shared_validators or {})
        for path in (self.state, paths.data / ".probe", paths.config / ".probe"):
            self.files.validate(path)
        self.backups = BackupStore(self.files, paths.state)

    def planner(self) -> Planner:
        return Planner(self.files, self.state, self.allowed,
                       self.section_readers, self.shared_validators)

    def _validate(self, plan: Plan) -> None:
        # Rebuild from authorized targets and current ownership; don't trust a
        # hand-constructed or stale Plan object to bypass planner policy.
        planner = self.planner()
        if planner.before != plan.manifest_before:
            raise ConflictError("State manifest changed since planning")
        for item in plan.changes:
            if self.files.read(item.path) != item.expected:
                raise ConflictError(f"File changed since planning: {item.path}")
            if item.action == "remove":
                planner.remove(item.path, owner=item.owner, reason=item.reason)
            elif item.action in {"create", "update"} and item.content is not None:
                planner.write(item.path, item.content, owner=item.owner, reason=item.reason,
                              shared=item.ownership == "shared", mode=item.mode,
                              sections=item.sections, release=item.release)
            else:
                raise SafetyError("Invalid planned action")
        if planner.build() != plan:
            raise SafetyError("Plan is inconsistent with its ownership manifest")

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self.files.private_directory(self.paths.state, create=True)
        path = self.paths.state / "transaction.lock"
        with self.files.parent(path) as directory:
            fd = os.open(path.name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                         0o600, dir_fd=directory)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600):
                    raise SafetyError("Insecure transaction lock")
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise ConflictError("Another AeroNox transaction is running") from exc
                yield
            finally:
                os.close(fd)

    def execute(self, plan: Plan, *, dry_run: bool = False) -> str | None:
        self._validate(plan)
        if dry_run or not plan.changes:
            return None
        if os.geteuid() == 0:
            raise SafetyError("AeroNox refuses mutations as root")
        with self._lock():
            self._validate(plan)
            # The manifest is committed last, and backed up like any other target.
            state_change = PlannedChange(
                self.state, "create" if plan.manifest_before is None else "update",
                plan.manifest_before, plan.manifest.serialize(), 0o600,
                "aeronox", "generated", "Record resource ownership",
            )
            changes = (*plan.changes, state_change)
            backup_id = self.backups.prepare(changes)
            attempted: list[PlannedChange] = []
            written: dict[Path, FileSnapshot | None] = {}
            try:
                for item in changes:
                    attempted.append(item)
                    if item.content is None:
                        assert item.expected is not None
                        self.files.remove(item.path, item.expected)
                    else:
                        self.files.replace(item.path, item.content, item.expected, mode=item.mode)
                    after = self.files.read(item.path)
                    if item.content is None:
                        matches = after is None
                    else:
                        matches = (after is not None and after.content == item.content
                                   and after.mode == item.mode)
                    if not matches:
                        raise ConflictError("A resource changed immediately after writing")
                    written[item.path] = after
                self.backups.mark(backup_id, "committed")
            except BaseException as exc:
                conflicts = self._rollback(attempted, written)
                try:
                    status = "recovery_required" if conflicts else "rolled_back"
                    self.backups.mark(backup_id, status, conflicts)
                except (OSError, SafetyError):
                    conflicts = (*conflicts, "journal status could not be saved")
                raise TransactionError(backup_id, conflicts) from exc
            return backup_id

    def _rollback(
        self, attempted: list[PlannedChange], written: dict[Path, FileSnapshot | None],
    ) -> tuple[str, ...]:
        conflicts = []
        for item in reversed(attempted):
            try:
                current = self.files.read(item.path)
                if current == item.expected:
                    continue
                if item.path in written:
                    ours = current == written[item.path]
                else:
                    # A syscall may have succeeded before a following fsync/read failed.
                    # Without the post-write fingerprint, leave recovery evidence.
                    ours = False
                if not ours:
                    raise ConflictError("Concurrent edit during rollback")
                if item.expected is None:
                    if current is not None:
                        self.files.remove(item.path, current)
                else:
                    self.files.replace(item.path, item.expected.content, current,
                                       mode=item.expected.mode, restore=item.expected)
            except (OSError, SafetyError):
                conflicts.append(str(item.path))
        return tuple(conflicts)
