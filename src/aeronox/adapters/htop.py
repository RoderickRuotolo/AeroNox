"""Separate htoprc copies; monochrome follows the parent terminal's colors."""

import os
import re
from pathlib import Path

from aeronox.adapters.generated import GeneratedAdapter
from aeronox.catalog import PaletteCatalog
from aeronox.models import PALETTE_IDS
from aeronox.paths import XDGPaths
from aeronox.planning import Plan
from aeronox.storage import ConflictError, FileSnapshot, SafetyError

COLOR_LINE = re.compile(rb"([ \t]*color_scheme[ \t]*=[ \t]*)([^\r\n]*)(\r?\n)?")


def monochrome_config(content: bytes) -> bytes:
    if b"\x00" in content or b"\r" in content.replace(b"\r\n", b""):
        raise SafetyError("Unsupported htoprc encoding or line endings")
    newline = b"\r\n" if b"\r\n" in content else b"\n"
    lines = content.splitlines(keepends=True)
    matches = [(index, match) for index, line in enumerate(lines)
               if (match := COLOR_LINE.fullmatch(line)) is not None]
    if len(matches) > 1:
        raise SafetyError("Duplicate color_scheme settings; review the source htoprc")
    if matches:
        index, match = matches[0]
        value = match.group(2)
        comment = b" #" + value.split(b"#", 1)[1] if b"#" in value else b""
        lines[index] = match.group(1) + b"1" + comment + (match.group(3) or b"")
        return b"".join(lines)
    prefix = newline if content and not content.endswith(b"\n") else b""
    return content + prefix + b"color_scheme=1" + newline


class HtopAdapter(GeneratedAdapter):
    name = "htop"

    def __init__(self, home: Path | None = None, paths: XDGPaths | None = None):
        home = Path.home() if home is None else home
        paths = XDGPaths.resolve() if paths is None else paths
        self.config_path = paths.config.parent / "htop/htoprc"
        targets = {palette_id: paths.data / "htop" / palette_id / "htoprc"
                   for palette_id in PALETTE_IDS}
        super().__init__(home, paths, targets)

    def _source(self) -> tuple[Path, FileSnapshot | None]:
        explicit = os.environ.get("HTOPRC")
        candidates = ([Path(explicit)] if explicit else [self.config_path, self.home / ".htoprc"])
        for path in candidates:
            if path in self.targets.values():
                raise SafetyError("HTOPRC points to a managed copy; unset it before installation")
            snapshot = self.store.files.read(path)
            if snapshot is not None:
                return path, snapshot
        return candidates[0], None

    def plan_install(self, palette_catalog: PaletteCatalog) -> Plan:
        planner = self.store.planner()
        source_path, source = self._source()
        content = monochrome_config(source.content if source else b"")
        for palette in palette_catalog.list():
            planner.write(self.targets[palette.id], content, owner=self.name,
                          reason="Copy htop preferences with native monochrome colors")
        if self.store.files.read(source_path) != source:
            raise ConflictError("Source htoprc changed during planning")
        return planner.build()

    def open_command(self, palette_id: str, args: list[str]) -> list[str]:
        executable = self.executable()
        if palette_id == "original":
            return [executable, *args]
        self.require_palette(palette_id)
        return [executable, "-C", *args]

    def launch_environment(self, palette_id: str) -> dict[str, str]:
        if palette_id == "original":
            return {}
        path = self.require_palette(palette_id)
        state_home = self.paths.state / "htop" / palette_id / "state"
        # Validate existing ancestors and the known native history destination;
        # missing directories are left for htop, including during dry-run.
        self.store.files.read(state_home / "htop/htop_history")
        return {"HTOPRC": str(path),
                "XDG_STATE_HOME": str(state_home)}
