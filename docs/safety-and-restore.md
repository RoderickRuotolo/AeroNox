# Safety engine (roadmap stages 2–4)

The transaction engine is used by the Terminator, htop and Vim adapters. The CLI exposes
`install`/`install --dry-run`, `backup list` and three application launchers. Installation
is the explicit operation that mutates the shared Terminator config or generated
htop/Vim files. Original htoprc and Vim startup files are never rewritten. See
[application notes](apps.md) for the supported native paths and profile behavior.

## Plans and ownership

An adapter supplies an exact whitelist of target files to `TransactionStore`.
`Planner.write` and `Planner.remove` capture expected source bytes, SHA-256,
permissions, owner/group, modification/change times and inode identity. Plans
contain a reason, action, ownership and conflict rule. Their display shows paths
and byte counts, never file contents. Preparing and validating a dry-run does
not create directories, locks, backups or temporary files and launches no process.
Filesystem reads can still update access times according to filesystem policy.

`state.json` is versioned JSON containing the active mode (initially `original`)
and resources keyed by absolute path. Each record contains the owning adapter,
SHA-256, permissions and `generated` or `shared` ownership. Schema 2 also stores
per-section hashes; schema 1 remains readable and is backed up before migration on
an actual mutation. Unknown or corrupt
schemas and duplicate JSON fields are rejected instead of replaced.

An existing unmanaged file conflicts by default. An adapter may explicitly
enroll a shared configuration after producing a safe, section-preserving plan.
The Terminator policy enforces byte preservation outside owned blocks and stores
individual profile hashes; unrelated personal edits do not block reinstallation. That API is not exposed as a generic CLI overwrite option. The generic
engine never deletes shared files. The internal Terminator removal plan removes
only owned sections and releases their record; public uninstall orchestration is
pending. Modified, missing or differently owned managed resources/sections conflict.
Repeating an identical install plan is a no-op, including no additional backup.

## Filesystem boundary

All mutation targets, including XDG metadata, must be inside an existing HOME.
XDG roots outside HOME are refused; an explicit external-root approval mechanism
is not implemented. XDG path resolution itself remains compatible with the XDG
standard. HOME cannot be `/`. Directories are traversed with pinned file descriptors
and `O_NOFOLLOW`; ancestors outside HOME are never created. Symlinks (including
HOME ancestors), hardlinks, special files, foreign owners, special permission bits,
extended attributes/ACLs and files over 16 MiB are refused. ACL/xattr preservation
is not implemented, so such files are never silently replaced without metadata.
Personal `.vimrc`, `.bashrc`, `.zshrc` and `settings.json` paths are protected even
if accidentally whitelisted. Root mutations are refused.

The implementation targets Linux/POSIX and uses `fcntl`, descriptor-relative
filesystem operations and directory `fsync`. It makes no portability guarantee
for Windows or filesystems that do not support these primitives.

## Transaction sequence

1. Rebuild and validate the plan against the whitelist and current ownership.
2. Acquire a nonblocking exclusive writer lock and revalidate the complete plan.
3. Snapshot all prior file bytes and metadata, including the prior manifest, to
   `$XDG_STATE_HOME/aeronox/backups/<UTC timestamp>-<random ID>/`.
4. Persist a `prepared` journal before changing target files. Creation entries
   record that no prior file existed. Entries also record planned resulting hashes.
5. Write a temporary file beside each destination, preserve owner/group and mode,
   flush and `fsync`, recheck the expected source and use `os.replace`. Removals
   likewise recheck the source. Sync the parent directory after each operation.
6. Write the ownership manifest last, then mark the journal `committed`.

Metadata directories must have mode `0700`, and snapshot blobs, journals, state
and lock files have mode `0600`. Existing insecure modes are refused, not silently
changed. Backup blobs deliberately use `0600`; original modes are recorded in the
journal. Their checksums and sizes are verified by `BackupStore.read_blob`.

The writer lock serializes cooperating AeroNox processes. Hashes, metadata and
inode fingerprints detect edits between planning and execution and at operation
boundaries. A check and a replacement are separate syscalls: there is a narrow
race against arbitrary external writers. This is not a filesystem-wide atomic
transaction or a guarantee against malicious concurrent processes under the same
user account. Close configuration editors while installing. Network/distributed
filesystems and power-loss durability are not certified.

## Failures and recovery

On a caught failure, including KeyboardInterrupt, completed changes are rolled
back in reverse order only when the current fingerprint still matches the engine's
post-write snapshot. Original bytes, owner/group, mode and modification time are
restored. A file edited or removed externally is preserved and reported as a
conflict. If a write may have completed but its post-write state could not be
confirmed, it is left for manual recovery rather than guessed at.

Journals end in `committed`, `rolled_back` or `recovery_required`. A process kill,
power loss or failure to save journal status can leave `prepared`, an incomplete
snapshot directory or an unreferenced temporary file. Snapshot/lock directories
and newly created empty target directories may remain after rollback. No backup
pruning or automatic crash recovery is implemented.

To investigate a failed transaction:

1. Stop other AeroNox writers and config editors. Run `aeronox backup list` and
   note the transaction ID. A malformed or insecure journal produces an error;
   it is not silently skipped as a valid backup.
2. Inspect its private `journal.json` locally. Each entry provides the original
   path, prior checksum, size, mode, UID/GID, mtime, snapshot filename and planned
   resulting checksum. `conflicts` identifies resources requiring review.
3. Use the internal `BackupStore.read_blob(id, index)` to validate a snapshot
   checksum before considering recovery. Compare the current resource with both
   recorded checksums. A differing current file must be preserved separately.
4. Recover individual original bytes and recorded metadata only after review.
   Never bulk-copy snapshots over live configurations. A creation entry has no
   original bytes and cannot justify deleting a subsequently edited file.

There is intentionally no `backup restore` command yet. The future `restore`
command returns active mode to `original`; it will not bulk-overwrite personal
configs. The active-theme commands and uninstall orchestration belong to stage 6.

## Validation

`tests/test_backup_restore.py` is collected by pytest and also runs independently
with `python -m unittest discover -s tests -p test_backup_restore.py -v` after
installing the package. All writes use synthetic files in temporary HOME/XDG trees.
Coverage includes creation/update/removal, snapshots, no-op installs, shared files,
protected paths, symlinks, hardlinks, FIFO, permissions, ownership, malformed JSON,
backup corruption, lock contention, concurrent edits and injected failures during
writing and rollback. Real application configuration fixtures are not used.

## Application runtime writes

Transactions cover AeroNox installations/removals, not arbitrary side effects of
an explicitly launched application. htop can rewrite its managed htoprc and create
history files. The wrapper redirects its state history under AeroNox state and
refuses unexpected symlinks in existing history paths. Such runtime data is not
silently accepted into manifest ownership and is not automatically deleted.
A rewritten copy causes a conflict on subsequent managed use/install/removal;
keep it for review. Existing normal htop commands remain available outside wrappers.
Vim launches keep personal startup settings and arguments in effect, so plugins
and user-supplied commands retain their ordinary behavior. Headless tests use
`-Nu NONE -i NONE -n` and temporary HOME/XDG to avoid dotfiles and swap/viminfo writes.

A multi-component install uses independent transactions. A failure in a later
component preserves earlier committed components and reports their outcomes and
backup IDs. The failing component still follows its rollback/recovery contract.
