"""XDG Vim colorschemes with True Color and xterm-256 approximations."""

from pathlib import Path

from aeronox.adapters.generated import GeneratedAdapter
from aeronox.catalog import PaletteCatalog
from aeronox.models import Palette
from aeronox.paths import XDGPaths
from aeronox.planning import Plan
from aeronox.storage import SafetyError

SCHEME_NAMES = {"aviation-red": "aeronox_red", "nvis-green-a": "aeronox_green"}
# Semantic roles stay central; groups only select roles and non-color emphasis.
GROUPS = {
    "Normal": ("foreground", "background", "NONE"),
    "Comment": ("foreground_muted", None, "italic"),
    "Constant": ("accent", None, "NONE"),
    "String": ("foreground", None, "NONE"),
    "Identifier": ("foreground", None, "NONE"),
    "Statement": ("accent", None, "bold"),
    "PreProc": ("accent", None, "NONE"),
    "Type": ("accent", None, "bold"),
    "Special": ("accent", None, "underline"),
    "LineNr": ("foreground_muted", "background", "NONE"),
    "CursorLine": (None, "background_alt", "NONE"),
    "Visual": (None, "selection", "NONE"),
    "StatusLine": ("foreground", "background_alt", "bold"),
    "Search": ("background", "accent", "bold"),
    "ErrorMsg": ("accent", "background_alt", "bold,reverse"),
    "WarningMsg": ("accent", "background_alt", "bold,underline"),
    "DiffAdd": ("foreground", "background_alt", "underline"),
    "DiffDelete": ("accent", "background_alt", "bold,reverse"),
    "Cursor": ("background", "cursor", "NONE"),
}


def xterm256(color: str) -> int:
    rgb = tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))
    levels = (0, 95, 135, 175, 215, 255)
    cube = [(16 + 36 * r + 6 * g + b, (red, green, blue))
            for r, red in enumerate(levels) for g, green in enumerate(levels)
            for b, blue in enumerate(levels)]
    grays = [(232 + i, (8 + 10 * i,) * 3) for i in range(24)]
    return min(cube + grays, key=lambda item: sum((a - b) ** 2
               for a, b in zip(rgb, item[1], strict=True)))[0]


def colorscheme(palette: Palette) -> bytes:
    lines = ['" AeroNox generated colorscheme; inspired, not NVIS certified.',
             "set background=dark", "highlight clear", 'if exists("syntax_on")',
             "  syntax reset", "endif", f"let g:colors_name = '{SCHEME_NAMES[palette.id]}'"]
    for group, (fg_role, bg_role, style) in GROUPS.items():
        fg = palette.colors[fg_role] if fg_role else "NONE"
        bg = palette.colors[bg_role] if bg_role else "NONE"
        cterm_fg = str(xterm256(fg)) if fg_role else "NONE"
        cterm_bg = str(xterm256(bg)) if bg_role else "NONE"
        lines.append(f"highlight {group} guifg={fg} guibg={bg} gui={style} "
                     f"ctermfg={cterm_fg} ctermbg={cterm_bg} cterm={style}")
    return ("\n".join(lines) + "\n").encode()


def vim_quote(value: str) -> str:
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise SafetyError("Control characters in Vim runtime paths are not supported")
    return "'" + value.replace("'", "''") + "'"


class VimAdapter(GeneratedAdapter):
    name = "vim"

    def __init__(self, home: Path | None = None, paths: XDGPaths | None = None):
        home = Path.home() if home is None else home
        paths = XDGPaths.resolve() if paths is None else paths
        self.runtime = paths.data / "vim"
        vim_quote(str(self.runtime))
        self.config_path = self.runtime / "colors"
        targets = {palette_id: self.config_path / f"{name}.vim"
                   for palette_id, name in SCHEME_NAMES.items()}
        super().__init__(home, paths, targets)

    def plan_install(self, palette_catalog: PaletteCatalog) -> Plan:
        planner = self.store.planner()
        for palette in palette_catalog.list():
            planner.write(self.targets[palette.id], colorscheme(palette), owner=self.name,
                          reason="Generate XDG Vim colorscheme without changing vimrc")
        return planner.build()

    def open_command(self, palette_id: str, args: list[str]) -> list[str]:
        executable = self.executable()
        if palette_id == "original":
            return [executable, *args]
        self.require_palette(palette_id)
        # runtimepath is a comma-separated option; quote separately for Vimscript.
        entry = str(self.runtime).replace("\\", "\\\\").replace(",", "\\,")
        command = (f"let &runtimepath = {vim_quote(entry)} . ',' . &runtimepath"
                   f" | colorscheme {SCHEME_NAMES[palette_id]}")
        return [executable, "-c", command, *args]
