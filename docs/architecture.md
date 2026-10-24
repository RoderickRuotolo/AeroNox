# Architecture through stage 2

- `models.py`, `catalog.py`: immutable validated palettes from bundled JSON.
- `paths.py`: read-only resolution of XDG roots.
- `planning.py`: strict ownership manifest, expected-source snapshots and immutable
  plans. An exact adapter whitelist is required; no implicit recursive write scope.
- `storage.py`: constrained descriptor-relative reads, atomic replacements,
  removals, metadata checks and content fingerprints.
- `backups.py`: private snapshots, checksums and versioned transaction journals.
- `transactions.py`: plan revalidation, cooperative writer lock, snapshot-first
  execution, manifest commit and conservative rollback.
- `commands.py`, `cli.py`: user-facing diagnostics, palette inspection, pending
  install plans and backup listing. No arbitrary-path write command is exposed.

There are no runtime dependencies outside the Python standard library. Modules
perform no filesystem mutations on import or object construction. Planning reads
files but never creates state; only nonempty, non-dry-run transaction execution
mutates files. Upcoming adapters will generate plans instead of implementing their
own backup and file replacement routines.

Stage 3 must introduce a ConfigObj-aware Terminator adapter, preserve `default`
byte for byte and handle ownership per generated profile inside a shared config.
The generic manifest currently fingerprints the whole shared file; independent
edits anywhere in it cause a conservative conflict. This limitation must be
addressed explicitly by the shared-section adapter before automatic uninstall.
See [safety and recovery](safety-and-restore.md) for the transaction contract.
