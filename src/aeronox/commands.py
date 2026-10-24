"""CLI orchestration; adapters own application-specific parsing and launch arguments."""

import json
import subprocess
from pathlib import Path

from aeronox.adapters.terminator import TerminatorAdapter
from aeronox.catalog import PaletteCatalog
from aeronox.paths import XDGPaths
from aeronox.transactions import TransactionStore

COMPONENTS = ("terminator", "htop", "vim", "vscode")


def component_names(value: str) -> tuple[str, ...]:
    names = tuple(value.split(","))
    if not names or len(set(names)) != len(names) or any(n not in COMPONENTS for n in names):
        raise ValueError("Use distinct components from: " + ",".join(COMPONENTS))
    return names


def install_components(
    components: tuple[str, ...], *, dry_run: bool, base_profile: str = "default",
) -> str:
    output = ["Dry-run only: no installation performed." if dry_run else "Installation report:"]
    for component in components:
        if component != "terminator":
            output.append(f"{component}: pending (adapter not implemented)")
            continue
        adapter = TerminatorAdapter(base_profile=base_profile)
        detection = adapter.detect()
        if not detection.available or not detection.supported:
            output.append(f"terminator: skipped ({detection.message})")
            continue
        plan = adapter.plan_install(PaletteCatalog())
        if dry_run:
            adapter.store.execute(plan, dry_run=True)
            output.extend(["terminator: two dedicated profiles planned", plan.describe(),
                           f"Manifest target: {adapter.store.state}",
                           f"Backup directory: {adapter.store.backups.root}"])
        else:
            result = adapter.install(plan)
            output.append(f"terminator: {result.message}")
            if result.backup_id:
                output.append(f"Backup: {result.backup_id}")
    return "\n".join(output)


def backup_list() -> str:
    store = TransactionStore(Path.home(), XDGPaths.resolve(), frozenset())
    backups = store.backups.list()
    if not backups:
        return "No AeroNox backups found."
    return "\n".join(f"{item['id']}: {item['status']} ({len(item['entries'])} file snapshots)"
                     for item in backups)


def open_terminator(palette_id: str | None, args: list[str], *, dry_run: bool) -> int:
    adapter = TerminatorAdapter()
    active = palette_id if palette_id is not None else adapter.store.planner().manifest.mode
    command = adapter.open_command(active, args)
    if dry_run:
        print(json.dumps(command))
        return 0
    return subprocess.run(command, check=False).returncode
