# Architecture through stage 3

- `models.py`, `catalog.py`: immutable validated palettes from bundled JSON.
- `paths.py`: read-only resolution of XDG roots.
- `planning.py`: strict ownership manifest, expected-source snapshots and immutable
  plans. An exact adapter whitelist is required; no implicit recursive write scope.
- `storage.py`: constrained descriptor-relative reads, atomic replacements,
  removals, metadata checks and content fingerprints.
- `backups.py`: private snapshots, checksums and versioned transaction journals.
- `transactions.py`: plan revalidation, cooperative writer lock, snapshot-first
  execution, manifest commit and conservative rollback.
- `adapters/base.py`: detection, install and verification results, plus the adapter
  Protocol. `Plan` wraps planned changes together with the expected manifest so
  execution can validate both; it replaces the bare change-list example in SPEC.
- `adapters/terminator_config.py`: ConfigObj semantic validation and a lossless
  section byte index. Only generated blocks are serialized with ConfigObj.
- `adapters/terminator.py`: native executable detection, section-aware installation,
  verification, internal removal planning and argument-vector construction.
- `commands.py`, `cli.py`: diagnostics, palettes, install orchestration, backup
  listing and the Terminator launcher. No arbitrary-path write command is exposed.

ConfigObj (5.0.8 or newer in the 5.x series) is a declared runtime dependency; its
upstream package keeps its own licensing notices. Modules perform no filesystem
mutations on import or object construction. Planning reads files but never creates
state; only nonempty, non-dry-run transaction execution mutates files. Launching
an application is a separate explicit CLI operation.

## Shared files

The manifest reader accepts schemas 1 and 2; writes use schema 2. The first actual
mutation snapshots the old manifest before migration. Dry-run and no-op operations
do not migrate it. Version 2 adds a `sections` hash dictionary to resource records;
older AeroNox versions reject this newer schema rather than misinterpreting it.
Recovery journal schema remains version 1.

The transaction store registers a section reader and an unowned-byte validator per
adapter. The planner verifies current owned section hashes and permits unrelated
personal edits when that policy is present. It also checks the proposed section
hashes, rejects unregistered name collisions and invokes the byte-preservation
validator. Rebuilding the plan under the writer lock repeats these checks. An
inconsistent or forged Plan cannot bypass the configured policy. Removing whole
shared files remains prohibited; the Terminator removal plan updates the file and
releases its ownership record after removing only registered blocks.

Generic shared records without section metadata retain the earlier conservative
whole-file conflict checks. There is no automatic adoption of unregistered existing
profiles, force-overwrite mode or generic section parser. Every future adapter must
provide its own constrained policy before allowing independent personal edits.
See [safety and recovery](safety-and-restore.md) and [application notes](apps.md).
