"""Read-only foundation CLI. Integration commands belong to later stages."""

import argparse
import json
import os
import platform
import shutil

from aeronox import __version__
from aeronox.catalog import PaletteCatalog
from aeronox.contrast import contrast_ratio
from aeronox.models import PaletteError
from aeronox.paths import XDGPaths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AeroNox low-light themes (foundation preview)")
    parser.add_argument("--version", action="version", version=f"aeronox {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Report availability without reading application configs")
    palette = commands.add_parser("palette", help="Inspect validated bundled palettes")
    actions = palette.add_subparsers(dest="action", required=True)
    actions.add_parser("list", help="List palettes")
    show = actions.add_parser("show", help="Show a palette as JSON")
    show.add_argument("palette_id")
    actions.add_parser("contrast", help="Report foreground/background sRGB contrast ratios")
    args = parser.parse_args(argv)
    catalog = PaletteCatalog()
    try:
        if args.command == "doctor":
            catalog.list()
            XDGPaths.resolve()
            print(f"Platform: {platform.system()} ({platform.machine()})")
            print(f"Python: {platform.python_version()}")
            linux_target = "yes" if platform.system() == "Linux" else "unsupported platform"
            print(f"Linux target: {linux_target}")
            for app in ("terminator", "htop", "vim", "code"):
                print(f"{app}: {'available' if shutil.which(app) else 'not found'}")
            truecolor = os.environ.get("COLORTERM", "").lower() in {"truecolor", "24bit"}
            color_status = "advertised (not verified)" if truecolor else "not advertised"
            print(f"True Color: {color_status}")
            print("XDG AeroNox locations: resolved (paths hidden)")
            print("Palettes: valid")
            print("Integrations and VS Code profiles: not implemented; no configs inspected")
        elif args.action == "list":
            for item in catalog.list():
                print(f"{item.id}: {item.name}")
        elif args.action == "show":
            print(json.dumps(catalog.get(args.palette_id).to_dict(), indent=2))
        else:
            for item in catalog.list():
                ratio = contrast_ratio(item.colors["foreground"], item.colors["background"])
                print(f"{item.id}: foreground/background {ratio:.2f}:1 (sRGB)")
            print("Numeric report only; no NVIS certification or medical benefit implied.")
    except (PaletteError, OSError) as exc:
        parser.exit(1, f"aeronox: {exc}\n")
    return 0
