"""State-only mode changes and atomic, conservative removal across all adapters."""

from pathlib import Path

from aeronox.adapters.htop import HtopAdapter
from aeronox.adapters.terminator import TerminatorAdapter
from aeronox.adapters.vim import VimAdapter
from aeronox.adapters.vscode import VSCodeAdapter
from aeronox.catalog import PaletteCatalog
from aeronox.paths import XDGPaths
from aeronox.planning import Plan, Planner
from aeronox.storage import ConflictError, SafetyError
from aeronox.transactions import TransactionStore


def state_store() -> TransactionStore:
    return TransactionStore(Path.home(), XDGPaths.resolve(), frozenset())


def current_mode() -> str:
    return state_store().planner().manifest.mode


def mode_plan(mode: str) -> tuple[TransactionStore, Plan]:
    if mode != "original":
        PaletteCatalog().get(mode)
    store = state_store()
    planner = store.planner()
    planner.set_mode(mode)
    return store, planner.build()


def change_mode(mode: str, *, dry_run: bool) -> str:
    store, plan = mode_plan(mode)
    backup_id = store.execute(plan, dry_run=dry_run)
    lines = ["Dry-run: no changes made." if dry_run else f"Active mode: {mode}",
             plan.describe()]
    if plan.mode_change is not None:
        lines.append(f"State target: {store.state}")
    if backup_id:
        lines.append(f"Backup: {backup_id}")
    lines.append("Only new launches use this mode; open windows are unchanged.")
    return "\n".join(lines)


def _replay(planner: Planner, plan: Plan) -> None:
    if plan.manifest_before != planner.before or plan.mode_change is not None:
        raise ConflictError("State changed while preparing removal")
    for item in plan.changes:
        if planner.files.read(item.path) != item.expected:
            raise ConflictError("Resource changed while preparing removal")
        if item.action == "remove":
            planner.remove(item.path, owner=item.owner, reason=item.reason)
        elif item.action == "update" and item.release and item.content is not None:
            planner.write(item.path, item.content, owner=item.owner, reason=item.reason,
                          shared=True, sections=item.sections, release=True)
        else:
            raise SafetyError("Unsupported adapter removal action")
        if planner.changes[-1] != item:
            raise ConflictError("Resource changed while combining removal plans")


def uninstall_plan() -> tuple[TransactionStore, Plan]:
    adapters = (TerminatorAdapter(), HtopAdapter(), VimAdapter(), VSCodeAdapter())
    allowed = frozenset(path for adapter in adapters for path in adapter.store.allowed)
    readers = {name: reader for adapter in adapters
               for name, reader in adapter.store.section_readers.items()}
    validators = {name: validator for adapter in adapters
                  for name, validator in adapter.store.shared_validators.items()}
    store = TransactionStore(Path.home(), XDGPaths.resolve(), allowed, readers, validators)
    planner = store.planner()
    conflicts = []
    for adapter in adapters:
        try:
            _replay(planner, adapter.plan_uninstall())
        except (SafetyError, OSError) as exc:
            conflicts.append(f"{adapter.name}: preserved ({exc})")
    remaining = planner.build().manifest.resources
    if remaining:
        conflicts.append(f"{len(remaining)} ownership record(s) cannot be safely removed; "
                         "review the manifest at " + str(store.state))
    if conflicts:
        raise ConflictError("Uninstall aborted; no changes made.\n" + "\n".join(conflicts)
                            + "\nRun restore to return to original mode without removing files.")
    planner.set_mode("original")
    return store, planner.build()


def uninstall(*, dry_run: bool) -> str:
    store, plan = uninstall_plan()
    backup_id = store.execute(plan, dry_run=dry_run)
    lines = ["Dry-run: no changes made." if dry_run else "Uninstall completed; mode original.",
             plan.describe()]
    if backup_id:
        lines.append(f"Backup: {backup_id}")
    lines.append("Backups, runtime history and manually configured VS Code profiles are retained.")
    return "\n".join(lines)
