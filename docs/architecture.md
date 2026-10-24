# Architecture through stage 4

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
- `adapters/generated.py`: native detection and common ownership/verification rules
  for complete generated files, reused by htop and Vim.
- `adapters/htop.py`: lossless source copying with one native monochrome override,
  per-palette target paths and launch-only environment deltas.
- `adapters/vim.py`: semantic highlight groups, nearest xterm-256 conversion,
  XDG colorschemes and safely quoted runtimepath selection.
- `commands.py`, `cli.py`: diagnostics, palettes, install orchestration, backup
  listing and Terminator/htop/Vim launchers. No arbitrary-path write command is exposed.

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

## Separate resources and orchestration

htop and Vim never enroll personal dotfiles. Each has two generated resources
under XDG data; whole-file hashes and modes guard installation, launch and removal.
htop reads an optional source snapshot at planning time without changing it. The
source is rechecked before returning the plan; later personal edits are picked up
by a future explicit installation, provided managed copies remain intact.

Launch argv and environment changes are separate from install transactions. The
htop launcher passes only HTOPRC and XDG_STATE_HOME overrides to the child; dry-run
prints only that delta. Vim prepends its XDG runtime directory to runtimepath via
an escaped Vimscript string in a separate `-c` argument. Other user startup settings
stay in effect. `original` mode delegates normally without generated resources.

Installations currently commit one transaction per component. The next component
plans against the newly committed manifest, preserving earlier ownership records.
If a later component fails, the CLI reports earlier commits and backup IDs. There
is no cross-component rollback or automatic adoption of a htop-rewritten copy.
These limits are explicit pending full integration/reconciliation in later stages.
