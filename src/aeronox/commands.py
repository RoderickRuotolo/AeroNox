"""CLI orchestration; adapters own application-specific parsing and launch arguments."""

import json
import os
import re
import subprocess
from pathlib import Path

from aeronox.adapters.htop import HtopAdapter
from aeronox.adapters.terminator import TerminatorAdapter
from aeronox.adapters.vim import VimAdapter
from aeronox.adapters.vscode import VSCodeAdapter, installations
from aeronox.catalog import PaletteCatalog
from aeronox.paths import XDGPaths
from aeronox.storage import SafetyError
from aeronox.transactions import TransactionStore

APPLICATIONS = ("terminator", "htop", "vim", "code")
COMPONENTS = ("terminator", "htop", "vim", "vscode")


def component_names(value: str) -> tuple[str, ...]:
    names = tuple(value.split(","))
    if not names or len(set(names)) != len(names) or any(n not in COMPONENTS for n in names):
        raise ValueError("Use distinct components from: " + ",".join(COMPONENTS))
    return names


def adapter_for(
    application: str, base_profile: str = "default", *, edition: str = "auto",
    user_data_dir: Path | None = None,
) -> TerminatorAdapter | HtopAdapter | VimAdapter | VSCodeAdapter:
    if application == "terminator":
        return TerminatorAdapter(base_profile=base_profile)
    if application == "htop":
        return HtopAdapter()
    if application == "vim":
        return VimAdapter()
    if application in {"code", "vscode"}:
        return VSCodeAdapter(edition=edition, user_data_dir=user_data_dir)
    raise SafetyError("Application integration is not implemented")


def install_components(
    components: tuple[str, ...], *, dry_run: bool, base_profile: str = "default",
    vscode_edition: str = "auto",
) -> str:
    output = ["Dry-run only: no installation performed." if dry_run else "Installation report:"]
    for component in components:
        try:
            adapter = adapter_for(component, base_profile, edition=vscode_edition)
            detection = adapter.detect()
            if not detection.available or not detection.supported:
                output.append(f"{component}: skipped ({detection.message})")
                continue
            plan = adapter.plan_install(PaletteCatalog())
            if dry_run:
                adapter.store.execute(plan, dry_run=True)
                description = ("two dedicated profiles planned" if component == "terminator"
                               else "two managed resources planned")
                if component == "vscode":
                    description = "two reference snippets planned (manual profile setup)"
                output.extend([f"{component}: {description}", plan.describe(),
                               f"Manifest target: {adapter.store.state}",
                               f"Backup directory: {adapter.store.backups.root}"])
            else:
                result = adapter.install(plan)
                output.append(f"{component}: {result.message}")
                if result.backup_id:
                    output.append(f"Backup: {result.backup_id}")
            if isinstance(adapter, VSCodeAdapter):
                output.append("Review setup: aeronox vscode guide (no profiles were configured)")
                output.extend(f"Snippet: {path}" for path in adapter.targets.values())
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
    edition: str = "auto", user_data_dir: Path | None = None,
) -> int:
    adapter = adapter_for(application, edition=edition, user_data_dir=user_data_dir)
    active = palette_id if palette_id is not None else adapter.store.planner().manifest.mode
    if isinstance(adapter, VSCodeAdapter) and active == "original" and palette_id is None:
        raise SafetyError("No active VS Code palette; prepare dedicated profiles (aeronox vscode "
                          "guide), then choose --palette. Use native code for normal opening.")
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


def vscode_status(
    edition: str = "auto", user_data_dir: Path | None = None, *, show_paths: bool = False,
) -> str:
    adapter = VSCodeAdapter(edition=edition, user_data_dir=user_data_dir)
    lines = [f"VS Code {item.edition}: " + (
        f"available ({item.kind})" if item.executable else "not found")
        for item in installations(adapter.home, adapter.paths)]
    selected = adapter.selected()
    lines.append(f"Selected edition: {selected.edition} ({selected.kind})")
    for palette in adapter.targets:
        lines.append(f"{palette}: {adapter.profile_status(palette)}")
    if show_paths:
        lines.append(f"Selected data root: {selected.data_root}")
        lines.extend(f"Snippet: {path}" for path in adapter.targets.values())
    return "\n".join(lines)


def diagnostic_paths() -> str:
    paths = XDGPaths.resolve()
    lines = [f"AeroNox config: {paths.config}", f"AeroNox state: {paths.state}",
             f"AeroNox data: {paths.data}"]
    for name in ("terminator", "htop", "vim"):
        lines.append(f"{name} default config/resource: {adapter_for(name).config_path}")
    selected = VSCodeAdapter().selected()
    if selected.kind == "native":
        lines.append(f"VS Code selected native data root: {selected.data_root}")
    else:
        lines.append("VS Code packaged/portable data root: manual setup required")
    return "\n".join(lines)


def versions_report() -> str:
    lines = []
    for application in APPLICATIONS:
        try:
            adapter = adapter_for(application)
            if isinstance(adapter, VSCodeAdapter) and adapter.selected().kind != "native":
                raise SafetyError("Manual edition")
            detection = adapter.detect()
            if not detection.supported or detection.executable is None:
                raise SafetyError("Unavailable edition")
            result = subprocess.run([detection.executable, "--version"], check=False,
                                    capture_output=True, text=True, errors="replace", timeout=3)
            first = result.stdout.splitlines()[0][:200] if result.stdout else ""
            match = re.search(r"\b\d+\.\d+(?:\.\d+)?(?:[-+][A-Za-z0-9.]+)?\b", first)
            version = match.group(0) if result.returncode == 0 and match else "unavailable"
        except (OSError, SafetyError, subprocess.TimeoutExpired):
            version = "unavailable (not probed or probe failed)"
        lines.append(f"{application} version: {version}")
    return "\n".join(lines)
