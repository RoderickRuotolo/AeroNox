"""Validated, immutable palette model."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

COLOR_ROLES = frozenset({
    "background", "background_alt", "foreground", "foreground_muted",
    "accent", "cursor", "selection",
})
PALETTE_IDS = ("aviation-red", "nvis-green-a")
HEX_RGB = re.compile(r"#[0-9a-fA-F]{6}")


class PaletteError(ValueError):
    """A palette does not satisfy schema version 1."""


@dataclass(frozen=True)
class Palette:
    schema_version: int
    id: str
    name: str
    description: str
    colors: Mapping[str, str]
    ansi16: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: object) -> "Palette":
        if not isinstance(data, dict):
            raise PaletteError("Palette must be a JSON object")
        required = {"schema_version", "id", "name", "description", "colors", "ansi16"}
        if set(data) != required:
            raise PaletteError("Palette requires exactly the schema version 1 fields")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise PaletteError("Unsupported schema_version (expected integer 1)")
        if data["id"] not in PALETTE_IDS:
            raise PaletteError("Unknown stable palette ID")
        for field in ("name", "description"):
            if not isinstance(data[field], str) or not data[field].strip():
                raise PaletteError(f"{field} must be a nonempty string")
        colors = data["colors"]
        if not isinstance(colors, dict) or set(colors) != COLOR_ROLES:
            raise PaletteError("colors must contain exactly the required semantic roles")
        ansi = data["ansi16"]
        if not isinstance(ansi, list) or len(ansi) != 16:
            raise PaletteError("ansi16 must contain exactly 16 colors")
        for value in [*colors.values(), *ansi]:
            if not isinstance(value, str) or HEX_RGB.fullmatch(value) is None:
                raise PaletteError("Colors must use #RRGGBB notation")
        return cls(1, data["id"], data["name"], data["description"],
                   MappingProxyType(dict(colors)), tuple(ansi))

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "id": self.id, "name": self.name,
                "description": self.description, "colors": dict(self.colors),
                "ansi16": list(self.ansi16)}
