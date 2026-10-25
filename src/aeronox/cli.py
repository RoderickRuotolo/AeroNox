"""CLI for palette inspection and safe, incremental application integrations."""

import argparse
import json
import os
import platform
import shutil
from pathlib import Path

from aeronox import __version__
from aeronox.adapters.vscode import EDITION_CHOICES, guide
from aeronox.adapters.vscode_theme import snippet
from aeronox.catalog import PaletteCatalog
from aeronox.commands import (
    APPLICATIONS,
    COMPONENTS,
    backup_list,
    component_names,
    diagnostic_paths,
    install_components,
    open_application,
    versions_report,
    vscode_status,
)
from aeronox.contrast import contrast_ratio
from aeronox.lifecycle import change_mode, current_mode, uninstall
from aeronox.models import PALETTE_IDS, PaletteError
from aeronox.paths import XDGPaths
from aeronox.storage import SafetyError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AeroNox low-light themes (incremental Linux preview)"
    )
    parser.add_argument("--version", action="version", version=f"aeronox {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor",
                                 help="Report availability and read-only VS Code profile readiness")
    doctor.add_argument("--paths", action="store_true", help="Include explicit local config paths")
    doctor.add_argument("--versions", action="store_true",
                        help="Run optional bounded native --version probes")
    apply = commands.add_parser("apply", help="Persist the mode used by new wrapper launches")
    apply.add_argument("palette_id", choices=PALETTE_IDS)
    apply.add_argument("--dry-run", action="store_true")
    commands.add_parser("current", help="Print active mode; absent state means original")
    restore = commands.add_parser("restore", help="Return mode to original without rewriting apps")
    restore.add_argument("--dry-run", action="store_true")
    remove = commands.add_parser("uninstall", help="Atomically remove only intact owned resources")
    remove.add_argument("--dry-run", action="store_true")
    install = commands.add_parser("install", help="Install dedicated profiles or preview a plan")
    install.add_argument("--dry-run", action="store_true", help="Plan without writing or launching")
    install.add_argument("--components", default=COMPONENTS, type=component_names,
                         help="Comma-separated: terminator,htop,vim,vscode")
    install.add_argument("--base-profile", default="default",
                         help="Existing Terminator profile to clone (default: default)")
    install.add_argument("--vscode-edition", choices=EDITION_CHOICES, default="auto",
                         help="Edition used to detect assisted VS Code setup")
    opener = commands.add_parser("open", help="Launch a supported application without a shell")
    applications = opener.add_subparsers(dest="application", required=True)
    for application in APPLICATIONS:
        child = applications.add_parser(application)
        child.add_argument("--palette", choices=("original", *PALETTE_IDS),
                           help="Override active mode for this launch only")
        child.add_argument("--dry-run", action="store_true",
                           help="Show launch plan without running")
        if application == "code":
            child.add_argument("--edition", choices=EDITION_CHOICES, default="auto")
            child.add_argument("--user-data-dir", type=Path,
                               help="Existing native data root inside HOME (read-only checks)")
        child.add_argument("app_args", nargs=argparse.REMAINDER,
                           help=f"Arguments to {application} after --")
    vscode = commands.add_parser("vscode",
                                 help="Offline guide, snippets and read-only profile status")
    assisted = vscode.add_subparsers(dest="vscode_action", required=True)
    assisted.add_parser("guide", help="Print manual dedicated-profile setup instructions")
    template = assisted.add_parser("snippet", help="Print generated reference settings JSONC")
    template.add_argument("palette_id", choices=PALETTE_IDS)
    status = assisted.add_parser("status", help="Inspect editions and dedicated profile readiness")
    status.add_argument("--edition", choices=EDITION_CHOICES, default="auto")
    status.add_argument("--user-data-dir", type=Path)
    status.add_argument("--paths", action="store_true", help="Include local data/snippet paths")
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
            print("VS Code: assisted integration; only dedicated profiles are inspected")
            try:
                print(vscode_status())
            except SafetyError:
                print("VS Code paths cannot be verified safely; use manual setup")
            if args.paths:
                print(diagnostic_paths())
            if args.versions:
                print(versions_report())
        elif args.command == "current":
            print(current_mode())
        elif args.command == "apply":
            print(change_mode(args.palette_id, dry_run=args.dry_run))
        elif args.command == "restore":
            print(change_mode("original", dry_run=args.dry_run))
        elif args.command == "uninstall":
            print(uninstall(dry_run=args.dry_run))
        elif args.command == "install":
            print(install_components(args.components, dry_run=args.dry_run,
                                     base_profile=args.base_profile,
                                     vscode_edition=args.vscode_edition))
        elif args.command == "open":
            app_args = args.app_args[1:] if args.app_args[:1] == ["--"] else args.app_args
            return open_application(args.application, args.palette, app_args, dry_run=args.dry_run,
                                    edition=getattr(args, "edition", "auto"),
                                    user_data_dir=getattr(args, "user_data_dir", None))
        elif args.command == "vscode":
            if args.vscode_action == "guide":
                print(guide(), end="")
            elif args.vscode_action == "snippet":
                print(snippet(catalog.get(args.palette_id)).decode(), end="")
            else:
                print(vscode_status(args.edition, args.user_data_dir, show_paths=args.paths))
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
