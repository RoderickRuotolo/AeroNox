"""CLI for palette inspection and safe, incremental application integrations."""

import argparse
import json
import os
import platform
import shutil

from aeronox import __version__
from aeronox.catalog import PaletteCatalog
from aeronox.commands import (
    APPLICATIONS,
    COMPONENTS,
    backup_list,
    component_names,
    install_components,
    open_application,
)
from aeronox.contrast import contrast_ratio
from aeronox.models import PALETTE_IDS, PaletteError
from aeronox.paths import XDGPaths
from aeronox.storage import SafetyError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AeroNox low-light themes (incremental Linux preview)"
    )
    parser.add_argument("--version", action="version", version=f"aeronox {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Report availability without reading application configs")
    install = commands.add_parser("install", help="Install dedicated profiles or preview a plan")
    install.add_argument("--dry-run", action="store_true", help="Plan without writing or launching")
    install.add_argument("--components", default=COMPONENTS, type=component_names,
                         help="Comma-separated: terminator,htop,vim,vscode")
    install.add_argument("--base-profile", default="default",
                         help="Existing Terminator profile to clone (default: default)")
    opener = commands.add_parser("open", help="Launch a supported application without a shell")
    applications = opener.add_subparsers(dest="application", required=True)
    for application in APPLICATIONS:
        child = applications.add_parser(application)
        child.add_argument("--palette", choices=("original", *PALETTE_IDS),
                           help="Override active mode for this launch only")
        child.add_argument("--dry-run", action="store_true",
                           help="Show launch plan without running")
        child.add_argument("app_args", nargs=argparse.REMAINDER,
                           help=f"Arguments to {application} after --")
    backups = commands.add_parser("backup", help="Inspect local transaction backups")
    backups.add_subparsers(dest="backup_action", required=True).add_parser("list")
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
            print("Terminator, htop and Vim adapters available; app versions not probed")
            print("VS Code integration: not implemented; no configs inspected")
        elif args.command == "install":
            print(install_components(args.components, dry_run=args.dry_run,
                                     base_profile=args.base_profile))
        elif args.command == "open":
            app_args = args.app_args[1:] if args.app_args[:1] == ["--"] else args.app_args
            return open_application(args.application, args.palette, app_args, dry_run=args.dry_run)
        elif args.command == "backup":
            print(backup_list())
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
    except (PaletteError, SafetyError, OSError) as exc:
        parser.exit(1, f"aeronox: {exc}\n")
    return 0
