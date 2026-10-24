"""Load palettes from packaged resources, independent of the working directory."""

import json
from importlib.resources import files

from aeronox.models import PALETTE_IDS, Palette, PaletteError


class PaletteCatalog:
    def get(self, palette_id: str) -> Palette:
        if palette_id not in PALETTE_IDS:
            raise PaletteError(f"Unknown palette: {palette_id}")
        resource = files("aeronox.palettes").joinpath(f"{palette_id}.json")
        try:
            palette = Palette.from_dict(json.loads(resource.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise PaletteError(f"Cannot load {palette_id}: {exc}") from exc
        if palette.id != palette_id:
            raise PaletteError("Palette ID does not match its resource name")
        return palette

    def list(self) -> tuple[Palette, ...]:
        return tuple(self.get(palette_id) for palette_id in PALETTE_IDS)
