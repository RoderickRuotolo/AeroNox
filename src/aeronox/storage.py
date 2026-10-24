"""Constrained filesystem primitives for plans and transactions (Linux/POSIX)."""

import hashlib
import json
import os
import secrets
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

MAX_FILE_SIZE = 16 * 1024 * 1024


class SafetyError(ValueError):
    """An operation violates the filesystem safety policy."""


class ConflictError(SafetyError):
    """A file no longer matches the reviewed plan or ownership record."""


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def decode_json(content: bytes) -> object:
    """Reject ambiguous duplicate fields in ownership and recovery records."""
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result

    return json.loads(content, object_pairs_hook=unique)


@dataclass(frozen=True)
class FileSnapshot:
    content: bytes
    mode: int
    uid: int
    gid: int
    mtime_ns: int
    ctime_ns: int
    device: int
    inode: int

    @property
    def sha256(self) -> str:
        return digest(self.content)

    def metadata(self) -> dict[str, object]:
        return {
            "sha256": self.sha256, "size": len(self.content), "mode": self.mode,
            "uid": self.uid, "gid": self.gid, "mtime_ns": self.mtime_ns,
        }


class SafeFiles:
    """Pin directory descriptors and refuse symlinks, hardlinks and special files.

    No paths are resolved through symlinks. Callers must separately authorize exact
    target files. Checking and replacing are separate syscalls: this is optimistic
    conflict detection, not a CAS against arbitrary concurrent external writers.
    """

    def __init__(self, home: Path):
        self.home = self._absolute(home)
        if self.home == Path("/"):
            raise SafetyError("HOME cannot be the filesystem root")

    @staticmethod
    def _absolute(path: Path) -> Path:
        if not path.is_absolute() or ".." in path.parts:
            raise SafetyError("Absolute paths without '..' are required")
        return path

    def validate(self, path: Path) -> None:
        self._absolute(path)
        if not path.is_relative_to(self.home) or path == self.home:
            raise SafetyError("Refusing a target outside HOME")

    @contextmanager
    def parent(self, path: Path, *, create: bool = False) -> Iterator[int]:
        self.validate(path)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        fd = os.open("/", flags)
        try:
            try:
                current = Path("/")
                for part in path.parent.parts[1:]:
                    current = current / part
                    if create and current != self.home and current.is_relative_to(self.home):
                        try:
                            os.mkdir(part, mode=0o700, dir_fd=fd)
                            os.fsync(fd)
                        except FileExistsError:
                            pass
                    child = os.open(part, flags, dir_fd=fd)
                    os.close(fd)
                    fd = child
            except OSError as exc:
                raise SafetyError(f"Cannot safely access {path}") from exc
            yield fd
        finally:
            os.close(fd)

    def _read(self, directory: int, name: str) -> FileSnapshot | None:
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return None
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise SafetyError("Only regular files with a single link are supported")
            if before.st_uid != os.geteuid():
                raise SafetyError("Refusing a file owned by another user")
            if before.st_mode & 0o7000:
                raise SafetyError("Refusing special permission bits")
            if os.listxattr(fd):
                raise SafetyError("Extended attributes and ACLs cannot be preserved yet")
            if before.st_size > MAX_FILE_SIZE:
                raise SafetyError("File exceeds the 16 MiB safety limit")
            chunks = []
            total = 0
            while chunk := os.read(fd, min(65536, MAX_FILE_SIZE + 1 - total)):
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_FILE_SIZE:
                    raise SafetyError("File exceeds the 16 MiB safety limit")
            after = os.fstat(fd)
            if before != after:
                # atime can change due to our read; compare mutation-related fields only.
                fields = ("st_size", "st_mtime_ns", "st_ctime_ns", "st_mode", "st_nlink",
                          "st_uid", "st_gid")
                if any(getattr(before, key) != getattr(after, key) for key in fields):
                    raise ConflictError("File changed while it was being read")
            return FileSnapshot(
                b"".join(chunks), stat.S_IMODE(after.st_mode), after.st_uid, after.st_gid,
                after.st_mtime_ns, after.st_ctime_ns, after.st_dev, after.st_ino,
            )
        finally:
            os.close(fd)

    def read(self, path: Path) -> FileSnapshot | None:
        self.validate(path)
        try:
            with self.parent(path) as directory:
                return self._read(directory, path.name)
        except SafetyError as exc:
            if isinstance(exc.__cause__, FileNotFoundError):
                return None
            raise
        except OSError as exc:
            raise SafetyError(f"Cannot safely read {path}") from exc

    def replace(
        self, path: Path, content: bytes, expected: FileSnapshot | None, *, mode: int = 0o600,
        restore: FileSnapshot | None = None,
    ) -> None:
        if mode & ~0o777 or len(content) > MAX_FILE_SIZE:
            raise SafetyError("Unsupported permissions or file size")
        with self.parent(path, create=True) as directory:
            temp = f".aeronox-{secrets.token_hex(12)}.tmp"
            try:
                fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(content)
                    identity = restore or expected
                    if identity is not None:
                        os.fchown(stream.fileno(), identity.uid, identity.gid)
                    os.fchmod(stream.fileno(), mode)
                    stream.flush()
                    if restore is not None:
                        os.utime(stream.fileno(), ns=(restore.mtime_ns, restore.mtime_ns))
                    os.fsync(stream.fileno())
                if self._read(directory, path.name) != expected:
                    raise ConflictError(f"File changed since planning: {path}")
                os.replace(temp, path.name, src_dir_fd=directory, dst_dir_fd=directory)
                os.fsync(directory)
            finally:
                try:
                    os.unlink(temp, dir_fd=directory)
                except FileNotFoundError:
                    pass

    def remove(self, path: Path, expected: FileSnapshot) -> None:
        with self.parent(path) as directory:
            if self._read(directory, path.name) != expected:
                raise ConflictError(f"File changed since planning: {path}")
            os.unlink(path.name, dir_fd=directory)
            os.fsync(directory)

    def private_directory(self, path: Path, *, create: bool = False) -> None:
        """Validate private AeroNox metadata directories without changing existing modes."""
        with self.parent(path / ".probe", create=create) as directory:
            info = os.fstat(directory)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise SafetyError(f"Metadata directory must be owned by you and mode 0700: {path}")

    def names(self, path: Path) -> list[str]:
        try:
            with self.parent(path / ".probe") as directory:
                return sorted(os.listdir(directory))
        except SafetyError as exc:
            if isinstance(exc.__cause__, FileNotFoundError):
                return []
            raise
