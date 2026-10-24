"""Adversarial safety tests; runnable with pytest or the standard library."""

import fcntl
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aeronox.cli import main
from aeronox.paths import XDGPaths
from aeronox.planning import Manifest
from aeronox.storage import ConflictError, SafeFiles, SafetyError, digest
from aeronox.transactions import TransactionError, TransactionStore


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="aeronox safety ")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / "home with spaces"
        self.home.mkdir(mode=0o700)
        env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "config"),
               "XDG_STATE_HOME": str(self.home / "state"),
               "XDG_DATA_HOME": str(self.home / "data")}
        environment = patch.dict(os.environ, env)
        environment.start()
        self.addCleanup(environment.stop)
        self.paths = XDGPaths.resolve()
        self.first = self.paths.data / "synthetic/first.txt"
        self.second = self.paths.data / "synthetic/second.txt"
        self.personal = self.home / "config/synthetic/personal.conf"
        self.allowed = frozenset({self.first, self.second, self.personal})
        self.store = TransactionStore(self.home, self.paths, self.allowed)

    def write_plan(self, content=b"generated\n", target=None):
        planner = self.store.planner()
        planner.write(target or self.first, content, owner="synthetic", reason="Test resource")
        return planner.build()

    def install(self):
        backup_id = self.store.execute(self.write_plan())
        self.assertIsNotNone(backup_id)
        return backup_id

    def tree(self):
        return {str(path.relative_to(self.home)): (
            stat.S_IMODE(path.lstat().st_mode), path.read_bytes() if path.is_file() else None,
        ) for path in self.home.rglob("*")}

    def test_plan_and_dry_run_have_no_side_effects(self):
        before = self.tree()
        plan = self.write_plan(b"PRIVATE USER CONTENT")
        self.assertIn(str(self.first), plan.describe())
        self.assertNotIn("PRIVATE USER CONTENT", plan.describe())
        self.assertIn("create", plan.describe())
        self.store.execute(plan, dry_run=True)
        self.assertEqual(self.tree(), before)

    def test_install_snapshots_and_manifest(self):
        backup_id = self.install()
        self.assertEqual(self.first.read_bytes(), b"generated\n")
        manifest = json.loads(self.store.state.read_bytes())
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["mode"], "original")
        record = manifest["resources"][str(self.first)]
        self.assertEqual(record["sha256"], digest(b"generated\n"))
        self.assertEqual(record["ownership"], "generated")
        journal = self.store.backups.inspect(backup_id)
        self.assertEqual(journal["status"], "committed")
        self.assertIsNone(self.store.backups.read_blob(backup_id, 0))
        self.assertEqual(journal["entries"][0]["after"]["sha256"], record["sha256"])
        for path in self.paths.state.rglob("*"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),
                             0o700 if path.is_dir() else 0o600)

    def test_idempotent_install_does_not_even_create_a_backup(self):
        self.install()
        before = self.tree()
        plan = self.write_plan()
        self.assertEqual(plan.changes, ())
        self.assertIsNone(self.store.execute(plan))
        self.assertEqual(self.tree(), before)

    def test_update_preserves_prior_bytes_and_metadata(self):
        self.install()
        before = self.first.stat()
        backup_id = self.store.execute(self.write_plan(b"replacement\n"))
        self.assertEqual(self.store.backups.read_blob(backup_id, 0), b"generated\n")
        entry = self.store.backups.inspect(backup_id)["entries"][0]["before"]
        self.assertEqual(entry["mtime_ns"], before.st_mtime_ns)
        self.assertEqual(entry["uid"], before.st_uid)
        self.assertEqual(entry["gid"], before.st_gid)
        self.assertEqual(entry["mode"], stat.S_IMODE(before.st_mode))
        self.assertEqual(entry["size"], len(b"generated\n"))
        self.assertIsNotNone(self.store.backups.read_blob(backup_id, 1))

    def test_shared_enrollment_requires_explicit_opt_in_and_preserves_mode(self):
        self.personal.parent.mkdir(parents=True)
        self.personal.write_bytes(b"# comment\nunknown = keep\n")
        self.personal.chmod(0o640)
        with self.assertRaises(ConflictError):
            self.write_plan(b"new", self.personal)
        planner = self.store.planner()
        planner.write(self.personal, b"# comment\nunknown = keep\ncolor = red\n",
                      owner="synthetic", reason="Preserve personal sections", shared=True)
        backup_id = self.store.execute(planner.build())
        self.assertEqual(self.store.backups.read_blob(backup_id, 0),
                         b"# comment\nunknown = keep\n")
        self.assertEqual(stat.S_IMODE(self.personal.stat().st_mode), 0o640)
        with self.assertRaises(ConflictError):
            self.store.planner().remove(self.personal, owner="synthetic", reason="Unsafe removal")

    def test_remove_only_intact_generated_resource(self):
        self.install()
        planner = self.store.planner()
        planner.remove(self.first, owner="synthetic", reason="Remove generated resource")
        backup_id = self.store.execute(planner.build())
        self.assertFalse(self.first.exists())
        self.assertEqual(self.store.backups.read_blob(backup_id, 0), b"generated\n")
        self.assertEqual(json.loads(self.store.state.read_bytes())["resources"], {})

    def test_modified_content_is_never_overwritten_or_removed(self):
        self.install()
        self.first.write_bytes(b"personal change")
        before = self.tree()
        with self.assertRaises(ConflictError):
            self.write_plan(b"replacement")
        with self.assertRaises(ConflictError):
            self.store.planner().remove(self.first, owner="synthetic", reason="remove")
        self.assertEqual(self.tree(), before)

    def test_modified_permissions_are_a_conflict(self):
        self.install()
        self.first.chmod(0o644)
        with self.assertRaises(ConflictError):
            self.write_plan()

    def test_deleted_managed_resource_is_a_conflict(self):
        self.install()
        self.first.unlink()
        with self.assertRaises(ConflictError):
            self.write_plan()

    def test_other_adapter_cannot_take_ownership(self):
        self.install()
        with self.assertRaises(ConflictError):
            self.store.planner().write(self.first, b"other", owner="other", reason="test")

    def test_whitelist_and_protected_startup_files(self):
        for name in (".vimrc", ".bashrc", ".zshrc", "settings.json", "unapproved"):
            path = self.home / name
            allowed = frozenset({path}) if name != "unapproved" else frozenset()
            store = TransactionStore(self.home, self.paths, allowed)
            with self.subTest(name=name), self.assertRaises(SafetyError):
                store.planner().write(path, b"bad", owner="synthetic", reason="test")
        with self.assertRaises(SafetyError):
            self.store.files.read(self.home / ".." / "outside")
        with self.assertRaises(SafetyError):
            self.store.files.read(Path("relative"))
        with self.assertRaises(SafetyError):
            self.store.files.read(Path(self.temporary.name) / "outside")

    def test_external_xdg_is_not_silently_authorized(self):
        external = Path(self.temporary.name) / "external state"
        paths = XDGPaths(self.paths.config, external, self.paths.data)
        with self.assertRaises(SafetyError):
            TransactionStore(self.home, paths, self.allowed)
        self.assertFalse(external.exists())

    def test_leaf_symlink_is_refused(self):
        self.first.parent.mkdir(parents=True)
        self.personal.parent.mkdir(parents=True)
        self.personal.write_bytes(b"personal")
        self.first.symlink_to(self.personal)
        with self.assertRaises(SafetyError):
            self.write_plan()
        self.assertEqual(self.personal.read_bytes(), b"personal")

    def test_dangling_symlink_is_refused(self):
        self.first.parent.mkdir(parents=True)
        self.first.symlink_to(self.home / "missing")
        with self.assertRaises(SafetyError):
            self.write_plan()

    def test_parent_symlink_is_refused(self):
        external = Path(self.temporary.name) / "external"
        external.mkdir()
        self.paths.data.parent.mkdir(parents=True, exist_ok=True)
        self.paths.data.symlink_to(external, target_is_directory=True)
        with self.assertRaises(SafetyError):
            self.write_plan()
        self.assertEqual(list(external.iterdir()), [])

    def test_hardlink_and_fifo_are_refused(self):
        self.first.parent.mkdir(parents=True)
        self.first.write_bytes(b"data")
        os.link(self.first, self.second)
        with self.assertRaises(SafetyError):
            self.write_plan()
        self.first.unlink()
        os.mkfifo(self.first)
        with self.assertRaises(SafetyError):
            self.write_plan()

    def test_duplicate_targets_are_refused(self):
        planner = self.store.planner()
        planner.write(self.first, b"one", owner="synthetic", reason="first")
        with self.assertRaises(SafetyError):
            planner.write(self.first, b"two", owner="synthetic", reason="second")

    def test_concurrent_creation_aborts_before_backups_or_mutations(self):
        plan = self.write_plan()
        self.first.parent.mkdir(parents=True)
        self.first.write_bytes(b"concurrent creation")
        before = self.tree()
        with self.assertRaises(ConflictError):
            self.store.execute(plan)
        self.assertEqual(self.tree(), before)

    def test_concurrent_edit_with_same_content_is_detected_by_fingerprint(self):
        self.install()
        plan = self.write_plan(b"replacement")
        self.first.write_bytes(b"generated\n")
        with self.assertRaises(ConflictError):
            self.store.execute(plan)

    def test_concurrent_manifest_change_is_detected(self):
        self.install()
        plan = self.write_plan(b"replacement")
        self.store.state.write_bytes(self.store.state.read_bytes() + b"\n")
        with self.assertRaises(ConflictError):
            self.store.execute(plan)
        self.assertEqual(self.first.read_bytes(), b"generated\n")

    def test_failure_rolls_back_update_creation_and_manifest(self):
        self.install()
        old_manifest = self.store.state.read_bytes()
        old_mtime = self.first.stat().st_mtime_ns
        planner = self.store.planner()
        planner.write(self.first, b"updated", owner="synthetic", reason="test")
        planner.write(self.second, b"new", owner="synthetic", reason="test")
        original = self.store.files.replace

        def fail_state(path, *args, **kwargs):
            if path == self.store.state:
                raise OSError("Injected failure")
            return original(path, *args, **kwargs)

        with patch.object(self.store.files, "replace", side_effect=fail_state):
            with self.assertRaises(TransactionError) as result:
                self.store.execute(planner.build())
        self.assertEqual(result.exception.conflicts, ())
        self.assertEqual(self.first.read_bytes(), b"generated\n")
        self.assertEqual(self.first.stat().st_mtime_ns, old_mtime)
        self.assertFalse(self.second.exists())
        self.assertEqual(self.store.state.read_bytes(), old_manifest)
        journal = self.store.backups.inspect(result.exception.backup_id)
        self.assertEqual(journal["status"], "rolled_back")

    def test_failure_after_removal_restores_resource(self):
        self.install()
        planner = self.store.planner()
        planner.remove(self.first, owner="synthetic", reason="test")
        original = self.store.files.replace

        def fail_state(path, *args, **kwargs):
            if path == self.store.state:
                raise OSError("Injected failure")
            return original(path, *args, **kwargs)

        with patch.object(self.store.files, "replace", side_effect=fail_state):
            with self.assertRaises(TransactionError):
                self.store.execute(planner.build())
        self.assertEqual(self.first.read_bytes(), b"generated\n")

    def test_rollback_preserves_concurrent_user_edits(self):
        self.install()
        planner = self.store.planner()
        planner.write(self.first, b"updated", owner="synthetic", reason="test")
        planner.write(self.second, b"new", owner="synthetic", reason="test")
        original = self.store.files.replace

        def edit_then_fail(path, *args, **kwargs):
            if path == self.second:
                self.first.write_bytes(b"concurrent personal edit")
                raise OSError("Injected failure")
            return original(path, *args, **kwargs)

        with patch.object(self.store.files, "replace", side_effect=edit_then_fail):
            with self.assertRaises(TransactionError) as result:
                self.store.execute(planner.build())
        self.assertIn(str(self.first), result.exception.conflicts)
        self.assertEqual(self.first.read_bytes(), b"concurrent personal edit")
        self.assertEqual(self.store.backups.inspect(result.exception.backup_id)["status"],
                         "recovery_required")
        self.assertEqual(self.store.backups.read_blob(result.exception.backup_id, 0),
                         b"generated\n")

    def test_failure_after_atomic_replace_leaves_precise_recovery_evidence(self):
        plan = self.write_plan()
        original = self.store.files.replace

        def fail_after_write(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == self.first:
                raise OSError("Simulated post-replace fsync failure")
            return result

        with patch.object(self.store.files, "replace", side_effect=fail_after_write):
            with self.assertRaises(TransactionError) as result:
                self.store.execute(plan)
        self.assertEqual(self.first.read_bytes(), b"generated\n")
        journal = self.store.backups.inspect(result.exception.backup_id)
        self.assertEqual(journal["status"], "recovery_required")
        self.assertEqual(journal["entries"][0]["after"]["sha256"],
                         digest(self.first.read_bytes()))

    def test_snapshot_failure_prevents_resource_mutation(self):
        plan = self.write_plan()
        with patch.object(self.store.backups, "prepare", side_effect=OSError("No space left")):
            with self.assertRaises(OSError):
                self.store.execute(plan)
        self.assertFalse(self.first.exists())
        self.assertFalse(self.store.state.exists())

    def test_backup_tampering_is_detected(self):
        self.install()
        backup_id = self.store.execute(self.write_plan(b"replacement"))
        blob = self.store.backups.directory(backup_id) / "0.bin"
        blob.write_bytes(b"corrupt")
        with self.assertRaises(SafetyError):
            self.store.backups.read_blob(backup_id, 0)
        with self.assertRaises(SafetyError):
            self.store.backups.read_blob("../../outside", 0)
        with self.assertRaises(SafetyError):
            self.store.backups.read_blob(backup_id, -1)

    def test_corrupt_manifest_is_never_replaced(self):
        self.install()
        for data in (b"{", b"{}", b'{"schema_version": true}',
                     b'{"schema_version": 99, "mode": "original", "resources": {}}'):
            self.store.state.write_bytes(data)
            with self.assertRaises(SafetyError):
                self.store.planner()
            self.assertEqual(self.store.state.read_bytes(), data)

    def test_insecure_state_directory_is_refused_without_chmod(self):
        self.paths.state.mkdir(parents=True, mode=0o755)
        plan = self.write_plan()
        with self.assertRaises(SafetyError):
            self.store.execute(plan)
        self.assertEqual(stat.S_IMODE(self.paths.state.stat().st_mode), 0o755)
        self.assertFalse(self.first.exists())

    def test_root_mutations_are_refused(self):
        plan = self.write_plan()
        with patch("aeronox.transactions.os.geteuid", return_value=0):
            with self.assertRaisesRegex(SafetyError, "root"):
                self.store.execute(plan)
        self.assertEqual(self.tree(), {})

    def test_transaction_lock_rejects_second_writer(self):
        plan = self.write_plan()
        self.store.files.private_directory(self.paths.state, create=True)
        lock = self.paths.state / "transaction.lock"
        fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ConflictError, "Another AeroNox"):
                self.store.execute(plan)
        finally:
            os.close(fd)
        self.assertFalse(self.first.exists())

    def test_replace_failure_cleans_temporary_file_and_preserves_original(self):
        self.first.parent.mkdir(parents=True)
        self.first.write_bytes(b"original")
        snapshot = self.store.files.read(self.first)
        with patch("aeronox.storage.os.replace", side_effect=OSError("Injected failure")):
            with self.assertRaises(OSError):
                self.store.files.replace(self.first, b"new", snapshot)
        self.assertEqual(self.first.read_bytes(), b"original")
        self.assertEqual(list(self.first.parent.iterdir()), [self.first])

    def test_backup_list_and_install_dry_run_are_read_only(self):
        from contextlib import redirect_stdout
        from io import StringIO

        output = StringIO()
        before = self.tree()
        with redirect_stdout(output):
            self.assertEqual(main(["install", "--dry-run"]), 0)
            self.assertEqual(main(["backup", "list"]), 0)
        self.assertEqual(self.tree(), before)
        self.assertIn("adapter not implemented", output.getvalue())
        self.assertIn("No AeroNox backups", output.getvalue())
        backup_id = self.install()
        before = self.tree()
        with redirect_stdout(output):
            self.assertEqual(main(["backup", "list"]), 0)
        self.assertIn(backup_id, output.getvalue())
        self.assertEqual(self.tree(), before)

    def test_manifest_outside_home_is_rejected(self):
        self.install()
        data = json.loads(self.store.state.read_bytes())
        data["resources"]["/outside/resource"] = data["resources"].pop(str(self.first))
        self.store.state.write_text(json.dumps(data))
        with self.assertRaises(SafetyError):
            Manifest.load(self.store.files.read(self.store.state), SafeFiles(self.home))


    def test_symlink_inserted_after_planning_does_not_touch_target(self):
        plan = self.write_plan()
        outside = Path(self.temporary.name) / "outside.txt"
        outside.write_bytes(b"outside")
        self.first.parent.mkdir(parents=True)
        self.first.symlink_to(outside)
        with self.assertRaises(SafetyError):
            self.store.execute(plan)
        self.assertEqual(outside.read_bytes(), b"outside")
        self.assertFalse(self.paths.state.exists())

    def test_foreign_owned_file_and_special_modes_are_refused(self):
        self.first.parent.mkdir(parents=True)
        self.first.write_bytes(b"personal")
        with patch("aeronox.storage.os.geteuid", return_value=os.geteuid() + 1):
            with self.assertRaises(SafetyError):
                self.store.files.read(self.first)
        self.first.chmod(0o4600)
        with self.assertRaises(SafetyError):
            self.store.files.read(self.first)

    def test_read_permission_failure_preserves_existing_file(self):
        self.first.parent.mkdir(parents=True)
        self.first.write_bytes(b"personal")
        self.first.chmod(0o000)
        try:
            with self.assertRaises(SafetyError):
                self.write_plan()
        finally:
            self.first.chmod(0o600)
        self.assertEqual(self.first.read_bytes(), b"personal")

    def test_private_metadata_symlinks_and_loose_permissions_are_refused(self):
        self.install()
        backups = self.store.backups.root
        backups.chmod(0o755)
        with self.assertRaises(SafetyError):
            self.store.backups.list()
        backups.chmod(0o700)
        backup_id = self.store.backups.list()[0]["id"]
        journal = self.store.backups.directory(backup_id) / "journal.json"
        journal.chmod(0o644)
        with self.assertRaises(SafetyError):
            self.store.backups.inspect(backup_id)
        journal.chmod(0o600)
        journal.unlink()
        journal.symlink_to(self.first)
        with self.assertRaises(SafetyError):
            self.store.backups.inspect(backup_id)

    def test_ambiguous_manifest_json_is_rejected(self):
        self.install()
        payload = (b'{"schema_version": 1, "mode": "original", "resources": {}, '
                   b'"resources": {}}')
        self.store.state.write_bytes(payload)
        with self.assertRaises(SafetyError):
            self.store.planner()

    def test_journal_cannot_redirect_snapshot_reads(self):
        self.install()
        backup_id = self.store.execute(self.write_plan(b"updated"))
        path = self.store.backups.directory(backup_id) / "journal.json"
        journal = json.loads(path.read_bytes())
        journal["entries"][0]["blob"] = "../../outside"
        path.write_text(json.dumps(journal))
        with self.assertRaises(SafetyError):
            self.store.backups.read_blob(backup_id, 0)

    def test_edit_between_write_and_post_check_is_preserved(self):
        plan = self.write_plan()
        original = self.store.files.replace

        def edit_after_write(path, *args, **kwargs):
            original(path, *args, **kwargs)
            if path == self.first:
                self.first.write_bytes(b"personal edit after rename")

        with patch.object(self.store.files, "replace", side_effect=edit_after_write):
            with self.assertRaises(TransactionError) as result:
                self.store.execute(plan)
        self.assertEqual(self.first.read_bytes(), b"personal edit after rename")
        self.assertIn(str(self.first), result.exception.conflicts)

    def test_keyboard_interrupt_rolls_back_completed_changes(self):
        self.install()
        planner = self.store.planner()
        planner.write(self.first, b"new", owner="synthetic", reason="test")
        planner.write(self.second, b"other", owner="synthetic", reason="test")
        original = self.store.files.replace

        def interrupt(path, *args, **kwargs):
            if path == self.second:
                raise KeyboardInterrupt
            return original(path, *args, **kwargs)

        with patch.object(self.store.files, "replace", side_effect=interrupt):
            with self.assertRaises(TransactionError) as result:
                self.store.execute(planner.build())
        self.assertEqual(result.exception.conflicts, ())
        self.assertEqual(self.first.read_bytes(), b"generated\n")

    def test_internal_metadata_cannot_become_an_adapter_target(self):
        store = TransactionStore(self.home, self.paths, frozenset({self.store.state}))
        with self.assertRaises(SafetyError):
            store.planner().write(self.store.state, b"bad", owner="synthetic", reason="test")



    def test_missing_home_does_not_create_ancestors_outside_home(self):
        missing = Path(self.temporary.name) / "absent parent" / "home"
        files = SafeFiles(missing)
        with self.assertRaises(SafetyError):
            files.replace(missing / "resource", b"data", None)
        self.assertFalse(missing.parent.exists())

    def test_extended_attributes_are_refused_rather_than_lost(self):
        self.first.parent.mkdir(parents=True)
        self.first.write_bytes(b"personal")
        try:
            os.setxattr(self.first, "user.aeronox_test", b"preserve me")
        except OSError:
            self.skipTest("Temporary filesystem does not support user xattrs")
        with self.assertRaises(SafetyError):
            self.write_plan()
        self.assertEqual(os.getxattr(self.first, "user.aeronox_test"), b"preserve me")
        self.assertEqual(self.first.read_bytes(), b"personal")

    def test_snapshot_exists_before_first_personal_file_mutation(self):
        self.personal.parent.mkdir(parents=True)
        self.personal.write_bytes(b"personal original")
        planner = self.store.planner()
        planner.write(self.personal, b"personal plus managed section", owner="synthetic",
                      reason="Synthetic section-preserving edit", shared=True)
        original = self.store.files.replace
        observed = []

        def check_snapshot(path, *args, **kwargs):
            if path == self.personal:
                journal = self.store.backups.list()[0]
                self.assertEqual(journal["status"], "prepared")
                self.assertEqual(self.store.backups.read_blob(journal["id"], 0),
                                 b"personal original")
                self.assertEqual(self.personal.read_bytes(), b"personal original")
                observed.append(True)
            return original(path, *args, **kwargs)

        with patch.object(self.store.files, "replace", side_effect=check_snapshot):
            self.store.execute(planner.build())
        self.assertEqual(observed, [True])

    def test_failed_journal_status_is_reported_with_backup_id(self):
        plan = self.write_plan()
        with patch.object(self.store.backups, "mark", side_effect=OSError("No space left")):
            with self.assertRaises(TransactionError) as result:
                self.store.execute(plan)
        self.assertFalse(self.first.exists())
        self.assertFalse(self.store.state.exists())
        self.assertIn("journal status could not be saved", result.exception.conflicts)
        self.assertEqual(self.store.backups.inspect(result.exception.backup_id)["status"],
                         "prepared")


if __name__ == "__main__":
    unittest.main()
