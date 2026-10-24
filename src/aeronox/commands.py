"""CLI orchestration; adapters own application-specific parsing and launch arguments."""

import json
import os
import subprocess
from pathlib import Path

from aeronox.adapters.htop import HtopAdapter
from aeronox.adapters.terminator import TerminatorAdapter
from aeronox.adapters.vim import VimAdapter
from aeronox.catalog import PaletteCatalog
from aeronox.paths import XDGPaths
from aeronox.storage import SafetyError
from aeronox.transactions import TransactionStore

APPLICATIONS = ("terminator", "htop", "vim")
COMPONENTS = ("terminator", "htop", "vim", "vscode")


def component_names(value: str) -> tuple[str, ...]:
    names = tuple(value.split(","))
    if not names or len(set(names)) != len(names) or any(n not in COMPONENTS for n in names):
        raise ValueError("Use distinct components from: " + ",".join(COMPONENTS))
    return names


def adapter_for(application: str, base_profile: str = "default") -> (
    TerminatorAdapter | HtopAdapter | VimAdapter
):
    if application == "terminator":
        return TerminatorAdapter(base_profile=base_profile)
    if application == "htop":
        return HtopAdapter()
    if application == "vim":
        return VimAdapter()
    raise SafetyError("Application integration is not implemented")


def install_components(
    components: tuple[str, ...], *, dry_run: bool, base_profile: str = "default",
) -> str:
    output = ["Dry-run only: no installation performed." if dry_run else "Installation report:"]
    for component in components:
        if component not in APPLICATIONS:
            output.append(f"{component}: pending (adapter not implemented)")
            continue
        try:
            adapter = adapter_for(component, base_profile)
            detection = adapter.detect()
            if not detection.available or not detection.supported:
                output.append(f"{component}: skipped ({detection.message})")
                continue
            plan = adapter.plan_install(PaletteCatalog())
            if dry_run:
                adapter.store.execute(plan, dry_run=True)
                description = ("two dedicated profiles planned" if component == "terminator"
                               else "two managed resources planned")
                output.extend([f"{component}: {description}", plan.describe(),
                               f"Manifest target: {adapter.store.state}",
                               f"Backup directory: {adapter.store.backups.root}"])
            else:
                result = adapter.install(plan)
                output.append(f"{component}: {result.message}")
                if result.backup_id:
                    output.append(f"Backup: {result.backup_id}")
        except (SafetyError, OSError) as exc:
            output.append(f"{component}: failed ({exc})")
            output.append("Stopped; earlier component transactions, if any, remain committed.")
            raise SafetyError("\n".join(output)) from exc
    return "\n".join(output)


def backup_list() -> str:
    store = TransactionStore(Path.home(), XDGPaths.resolve(), frozenset())
    backups = store.backups.list()
    if not backups:
        return "No AeroNox backups found."
    return "\n".join(f"{item['id']}: {item['status']} ({len(item['entries'])} file snapshots)"
                     for item in backups)


def open_application(
    application: str, palette_id: str | None, args: list[str], *, dry_run: bool,
) -> int:
    adapter = adapter_for(application)
    active = palette_id if palette_id is not None else adapter.store.planner().manifest.mode
    command = adapter.open_command(active, args)
    delta = adapter.launch_environment(active) if isinstance(adapter, HtopAdapter) else {}
    if dry_run:
        print(json.dumps({"argv": command, "env": delta} if delta else command))
        return 0
    if delta:
        return subprocess.run(command, check=False, env={**os.environ, **delta}).returncode
    return subprocess.run(command, check=False).returncode


def open_terminator(palette_id: str | None, args: list[str], *, dry_run: bool) -> int:
    return open_application("terminator", palette_id, args, dry_run=dry_run)
