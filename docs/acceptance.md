# MVP acceptance and validation status

All six roadmap implementation stages are present. This is an MVP, with explicit
validation/release gates below; it is not a certified or fully desktop-validated
product. SPEC.md remains the functional contract.

## Functional acceptance (SPEC section 9)

| Criterion | Implementation/evidence |
| --- | --- |
| Help and doctor without sudo | CLI smoke tests; paths and version probes are opt-in |
| Valid palettes and 16 ANSI entries | Catalog/model tests; generated VS Code asset drift check |
| install dry-run has no mutations | Unit/E2E tree comparisons and spawn guards |
| Preserve Terminator default/personal sections | Lossless ConfigObj indexing and exact byte comparisons |
| Two Terminator profiles | Native configuration syntax validation and profile ownership tests; GUI selection remains manual |
| Separate htoprc | Child-only HTOPRC; native PTY controls; original and legacy sources preserved |
| Vim schemes without vimrc edits | Native headless RGB/256-color checks and actual terminal recordings |
| VS Code assets and Default preserved | Packaged snippets/guide, synthetic registry checks; no Default-settings reads/writes |
| apply/current affect new wrapper launches | State-only transaction tests and installed CLI red/green sequence |
| restore returns mode original | No app file rewrites; explicit original Code launch remains the assisted-mode exception |
| Conservative uninstall | One combined transaction, intact resources only, conflict aborts all removal |
| Idempotent install/uninstall | Repeat CLI sequences compare resource/state/backup bytes |
| Adversarial filesystem cases | Symlinks, hardlinks, permissions, corrupt metadata, concurrent edits and failure injection |
| Temporary HOME/XDG | Fixtures, native smoke tests and installed CLI tests isolate all writes |
| Ubuntu ruff/pytest CI | Workflow configured; local tool availability is recorded in delivery results, not assumed |
| README and previews | English README, PT-BR quick start, safety/apps docs and four native terminal recordings |

## End-to-end scenarios (SPEC section 10)

1. **New user:** absent-state no-ops, generated resources without creating personal
   vimrc/default sections; missing applications are skipped.
2. **Advanced user:** synthetic Terminator profiles, layouts, plugins, comments,
   quoted/multiline settings and unknown sections retain original bytes.
3. **Repeated execution:** second install and uninstall introduce no duplicates or
   extra backups when no changes are needed.
4. **Personal change after install:** modified resources cause conflicts; nothing
   is deleted. restore remains available for valid state metadata.
5. **Interruption:** injected failures/KeyboardInterrupt test rollback or a private
   recovery journal. Final-state failure during uninstall restores all components.
6. **Custom XDG:** fixtures use HOME/XDG roots with spaces; native Vim also tests
   comma, quote, backslash and bar characters in runtime paths.
7. **Absent apps:** installed CLI uses an empty PATH and reports skipped adapters
   without writing application configs. Mode can still be selected independently.
8. **Vim without True Color:** both themes load headlessly with notermguicolors and
   verify the cterm attributes.
9. **Return to original:** installed CLI performs install, red, green, restore,
   uninstall; personal files and manually configured Code profiles remain intact.
10. **Unprepared VS Code:** opening prints setup instructions and does not start a
    process or implicitly create a profile. Themed launch requires verified settings.

`tests/test_lifecycle.py` covers atomic state/removal and error cases;
`tests/test_e2e.py` runs the installed CLI with fake children; native Vim/htop tests
exercise actual applications in isolated modes. `tests/test_captures.py` validates
committed real terminal recordings and palette metadata.

## Remaining validation/release gates

- Run ruff and the complete pytest suite in an environment with development tools;
  absent tools cannot be reported as passing. CI must be observed after push.
- Manually verify Terminator's GUI, VS Code profile appearance and actual terminal
  legibility in both palettes. No GUI session or personal dotfile was used here.
- Confirm licensing before publishing a release; MIT is still only the specification's
  proposal. Runtime dependencies keep their own upstream notices.

## Deliberate technical limits

- install commits per component and reports earlier commits if a later one fails;
  uninstall is atomic across all known components and returns mode to original.
- Unknown/outdated manifest destinations are retained as conflicts rather than
  removed through paths read from metadata alone.
- htop can rewrite its managed copy/history; divergent copies are preserved and
  require review before later managed use/removal. There is no auto-adoption/reset.
- restore changes only active mode, never bulk-copies backups over personal files.
  It does not repair corrupt or insecure state; recovery remains explicit/manual.
- Implicit Code opening in original mode shows guidance; explicit --palette original
  or native code is the intentional ordinary launch. Code settings remain manual.
- Filesystem/profile checks are optimistic between syscalls; private snapshots and
  journals support recovery. Cross-process power loss, malicious same-user races,
  network filesystems and every packaging variant are not certified.
- Existing windows stay as they are. No watcher, desktop theme change, brightness
  adjustment, network telemetry or automatic application installation is included.
