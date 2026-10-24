"""Resolve XDG locations without creating directories or reading dotfiles."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class XDGPaths:
    config: Path
    state: Path
    data: Path

    @classmethod
    def resolve(cls, env: Mapping[str, str] | None = None) -> "XDGPaths":
        environment = os.environ if env is None else env
        home = Path(environment["HOME"]) if environment.get("HOME") else Path.home()

        def location(key: str, default: str) -> Path:
            value = environment.get(key, "")
            # XDG explicitly requires absolute paths; ignore empty/relative values.
            base = Path(value) if value and Path(value).is_absolute() else home / default
            return base / "aeronox"

        return cls(location("XDG_CONFIG_HOME", ".config"),
                   location("XDG_STATE_HOME", ".local/state"),
                   location("XDG_DATA_HOME", ".local/share"))
