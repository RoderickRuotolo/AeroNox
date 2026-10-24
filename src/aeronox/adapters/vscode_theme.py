"""Deterministic assisted settings snippets derived from central semantic palettes."""

import json
from collections.abc import Mapping

from aeronox.models import Palette

PROFILE_NAMES = {"aviation-red": "AeroNox Aviation Red", "nvis-green-a": "AeroNox NVIS Green A"}
ANSI_NAMES = ("Black", "Red", "Green", "Yellow", "Blue", "Magenta", "Cyan", "White",
              "BrightBlack", "BrightRed", "BrightGreen", "BrightYellow", "BrightBlue",
              "BrightMagenta", "BrightCyan", "BrightWhite")


def theme_settings(palette: Palette) -> dict[str, object]:
    colors = palette.colors
    workbench = {
        "editor.background": colors["background"],
        "editor.foreground": colors["foreground"],
        "editorCursor.foreground": colors["cursor"],
        "editor.selectionBackground": colors["selection"],
        "editor.lineHighlightBackground": colors["background_alt"],
        "editorLineNumber.foreground": colors["foreground_muted"],
        "editorLineNumber.activeForeground": colors["accent"],
        "editorError.foreground": colors["accent"],
        "editorWarning.foreground": colors["foreground"],
        "activityBar.background": colors["background_alt"],
        "activityBar.foreground": colors["foreground"],
        "sideBar.background": colors["background_alt"],
        "sideBar.foreground": colors["foreground"],
        "statusBar.background": colors["background_alt"],
        "statusBar.foreground": colors["foreground"],
        "titleBar.activeBackground": colors["background_alt"],
        "titleBar.activeForeground": colors["foreground"],
        "tab.activeBackground": colors["background"],
        "tab.activeForeground": colors["accent"],
        "tab.inactiveBackground": colors["background_alt"],
        "tab.inactiveForeground": colors["foreground_muted"],
        "input.background": colors["background"],
        "input.foreground": colors["foreground"],
        "list.activeSelectionBackground": colors["selection"],
        "list.activeSelectionForeground": colors["foreground"],
        "panel.background": colors["background"],
        "focusBorder": colors["accent"],
        "terminal.background": colors["background"],
        "terminal.foreground": colors["foreground"],
        "terminalCursor.foreground": colors["cursor"],
        "terminal.selectionBackground": colors["selection"],
    }
    workbench.update({f"terminal.ansi{name}": color
                      for name, color in zip(ANSI_NAMES, palette.ansi16, strict=True)})
    tokens = [
        (["comment", "punctuation.definition.comment"], "foreground_muted", "italic"),
        (["string"], "foreground", ""),
        (["constant", "support.constant"], "accent", ""),
        (["keyword", "storage"], "accent", "bold"),
        (["entity.name.type", "support.type"], "accent", "bold"),
        (["entity.name.function", "support.function"], "accent", ""),
        (["variable", "meta.definition.variable"], "foreground", ""),
        (["invalid"], "accent", "bold underline"),
    ]
    return {
        "workbench.colorCustomizations": workbench,
        "editor.tokenColorCustomizations": {"textMateRules": [
            {"scope": scopes, "settings": {"foreground": colors[role], "fontStyle": style}}
            for scopes, role, style in tokens
        ]},
        "editor.semanticTokenColorCustomizations": {"enabled": True, "rules": {
            "comment": {"foreground": colors["foreground_muted"], "italic": True},
            "string": colors["foreground"], "number": colors["accent"],
            "keyword": {"foreground": colors["accent"], "bold": True},
            "type": {"foreground": colors["accent"], "bold": True},
            "function": colors["accent"], "variable": colors["foreground"],
            "variable.readonly": {"foreground": colors["accent"], "italic": True},
            "parameter": colors["foreground"], "property": colors["foreground"],
        }},
    }


def snippet(palette: Palette) -> bytes:
    heading = ("// AeroNox generated reference: merge manually into a dedicated profile.\n"
               "// Never replace your entire settings.json or edit Default automatically.\n"
               "// Inspired colors only; no NVIS certification or medical claims.\n")
    return (heading + json.dumps(theme_settings(palette), indent=2) + "\n").encode()


def contains_settings(actual: object, expected: object) -> bool:
    if isinstance(expected, Mapping):
        return isinstance(actual, Mapping) and all(
            key in actual and contains_settings(actual[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        # Generated TextMate rules must come last so prior profile rules remain possible.
        return (isinstance(actual, list) and len(actual) >= len(expected)
                and actual[-len(expected):] == expected)
    return type(actual) is type(expected) and actual == expected
