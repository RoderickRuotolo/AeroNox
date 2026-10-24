import json
from importlib.resources import files

import pytest

from aeronox.catalog import PaletteCatalog
from aeronox.contrast import contrast_ratio
from aeronox.models import Palette, PaletteError


def test_bundled_palettes():
    palettes = PaletteCatalog().list()
    assert [p.id for p in palettes] == ["aviation-red", "nvis-green-a"]
    assert [p.colors["background"] for p in palettes] == ["#050000", "#000500"]
    for palette in palettes:
        assert len(palette.ansi16) == 16
        assert Palette.from_dict(palette.to_dict()) == palette
        with pytest.raises(TypeError):
            palette.colors["background"] = "#FFFFFF"


@pytest.mark.parametrize("field,value", [
    ("schema_version", 2), ("schema_version", True), ("id", "../invalid"),
    ("name", " "), ("description", None), ("ansi16", ["#FFFFFF"] * 15),
    ("ansi16", ["#GGGGGG"] * 16), ("ansi16", [12] * 16),
    ("colors", {}), ("colors", {"background": "red"}),
])
def test_invalid_fields(field, value):
    data = PaletteCatalog().get("aviation-red").to_dict()
    data[field] = value
    with pytest.raises(PaletteError):
        Palette.from_dict(data)


@pytest.mark.parametrize("value", [None, [], {}, {"extra": True}])
def test_invalid_structure(value):
    with pytest.raises(PaletteError):
        Palette.from_dict(value)


@pytest.mark.parametrize("color", ["red", "#FFF", "#000000\n", None, 12])
def test_invalid_semantic_color(color):
    data = PaletteCatalog().get("aviation-red").to_dict()
    data["colors"]["foreground"] = color
    with pytest.raises(PaletteError):
        Palette.from_dict(data)


def test_missing_required_field():
    data = PaletteCatalog().get("aviation-red").to_dict()
    del data["description"]
    with pytest.raises(PaletteError):
        Palette.from_dict(data)


def test_unknown_id():
    with pytest.raises(PaletteError):
        PaletteCatalog().get("../../secret")


def test_resource_id_mismatch(monkeypatch, tmp_path):
    data = PaletteCatalog().get("nvis-green-a").to_dict()
    (tmp_path / "aviation-red.json").write_text(json.dumps(data))
    monkeypatch.setattr("aeronox.catalog.files", lambda _: tmp_path)
    with pytest.raises(PaletteError, match="does not match"):
        PaletteCatalog().get("aviation-red")


def test_malformed_resource(monkeypatch, tmp_path):
    (tmp_path / "aviation-red.json").write_text("{")
    monkeypatch.setattr("aeronox.catalog.files", lambda _: tmp_path)
    with pytest.raises(PaletteError, match="Cannot load"):
        PaletteCatalog().get("aviation-red")


def test_all_resource_json_valid():
    resources = files("aeronox.palettes")
    for palette in PaletteCatalog().list():
        assert json.loads(resources.joinpath(f"{palette.id}.json").read_text()) == palette.to_dict()


def test_contrast_reference_values():
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21)
    assert contrast_ratio("#123456", "#123456") == pytest.approx(1)
