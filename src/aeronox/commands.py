"""CLI boundary for the safety foundation; application adapters are still pending."""

from pathlib import Path

from aeronox.paths import XDGPaths
from aeronox.storage import SafetyError
from aeronox.transactions import TransactionStore

COMPONENTS = ("terminator", "htop", "vim", "vscode")


def component_names(value: str) -> tuple[str, ...]:
    names = tuple(value.split(","))
    if not names or len(set(names)) != len(names) or any(n not in COMPONENTS for n in names):
        raise ValueError("Use distinct components from: " + ",".join(COMPONENTS))
    return names


def install_preview(components: tuple[str, ...]) -> str:
    store = TransactionStore(Path.home(), XDGPaths.resolve(), frozenset())
    plan = store.planner().build()
    store.execute(plan, dry_run=True)
    pending = "\n".join(f"{name}: pending (adapter not implemented)" for name in components)
    return ("Dry-run only: no installation performed.\n" + pending + "\n" + plan.describe()
            + "\nManifest target (when changes exist): " + str(store.state)
            + "\nBackup directory (when changes exist): " + str(store.backups.root))


def backup_list() -> str:
    store = TransactionStore(Path.home(), XDGPaths.resolve(), frozenset())
    backups = store.backups.list()
    if not backups:
        return "No AeroNox backups found."
    return "\n".join(f"{item['id']}: {item['status']} ({len(item['entries'])} file snapshots)"
                     for item in backups)


def install_unavailable() -> None:
    raise SafetyError("Installation adapters are not implemented; use install --dry-run to inspect")
