"""Mode persistence and atomic uninstall use temporary HOME/XDG and synthetic configs."""

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from aeronox.adapters.htop import HtopAdapter
from aeronox.adapters.terminator import TerminatorAdapter
from aeronox.adapters.vim import VimAdapter
from aeronox.adapters.vscode import VSCodeAdapter
from aeronox.adapters.vscode_theme import PROFILE_NAMES, snippet
from aeronox.catalog import PaletteCatalog
from aeronox.cli import main
from aeronox.lifecycle import current_mode, mode_plan, state_store, uninstall_plan
from aeronox.planning import Resource
from aeronox.storage import ConflictError, SafetyError, digest
from aeronox.transactions import TransactionError

FIXTURES = Path(__file__).parent / "fixtures"


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aeronox lifecycle ")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / "home with spaces"
        self.home.mkdir(mode=0o700)
        environment = patch.dict(os.environ, {
            "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "config with spaces"),
            "XDG_STATE_HOME": str(self.home / "state"), "XDG_DATA_HOME": str(self.home / "data"),
            "HTOPRC": "", "VSCODE_PORTABLE": "",
        })
        environment.start()
        self.addCleanup(environment.stop)
        detection = patch("shutil.which", side_effect=lambda name: f"/synthetic/{name}")
        detection.start()
        self.addCleanup(detection.stop)

    def capture(self, args):
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(args)
        self.assertEqual(status, 0)
        return output.getvalue()

    def tree(self):
        return {str(p.relative_to(self.home)): (p.stat().st_mode,
                p.read_bytes() if p.is_file() else None) for p in self.home.rglob("*")}

    def fixtures(self):
        terminator = TerminatorAdapter().config_path
        htop = HtopAdapter().config_path
        for path, source in ((terminator, FIXTURES / "terminator/complex.conf"),
                             (htop, FIXTURES / "htop/custom.htoprc")):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.read_bytes())
        vimrc = self.home / ".vimrc"
        vimrc.write_bytes((FIXTURES / "vim/personal.vimrc").read_bytes())
        default = VSCodeAdapter().selected().data_root / "User/settings.json"
        default.parent.mkdir(parents=True, exist_ok=True)
        default.write_bytes(b'{"personal": "SYNTHETIC_DEFAULT"}')
        bashrc = self.home / ".bashrc"
        bashrc.write_bytes(b"# synthetic personal shell settings\n")
        return {p: p.read_bytes() for p in (terminator, htop, vimrc, default, bashrc)}

    def installed(self):
        original = self.fixtures()
        self.capture(["install"])
        return original

    def prepared_code(self):
        root = VSCodeAdapter().selected().data_root
        registry = root / "User/globalStorage/storage.json"
        entries = []
        for palette in PaletteCatalog().list():
            location = "synthetic-" + palette.id
            entries.append({"name": PROFILE_NAMES[palette.id], "location": location})
            settings = root / "User/profiles" / location / "settings.json"
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_bytes(snippet(palette))
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({"userDataProfiles": entries}))
        return {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def test_current_missing_restore_and_uninstall_are_read_only_noops(self):
        self.assertEqual(self.capture(["current"]), "original\n")
        self.capture(["restore"])
        self.capture(["uninstall"])
        self.assertEqual(self.tree(), {})

    def test_apply_persists_only_state_and_backup_not_application_files(self):
        self.installed()
        adapters = (TerminatorAdapter(), HtopAdapter(), VimAdapter(), VSCodeAdapter())
        paths = {p for adapter in adapters for p in adapter.store.allowed}
        before = {p: p.read_bytes() for p in paths}
        with patch("aeronox.commands.subprocess.run", side_effect=AssertionError("spawned")):
            output = self.capture(["apply", "aviation-red"])
        self.assertIn("new launches", output)
        self.assertEqual(self.capture(["current"]), "aviation-red\n")
        self.assertEqual({p: p.read_bytes() for p in paths}, before)
        self.assertEqual(state_store().state.stat().st_mode & 0o777, 0o600)

    def test_apply_without_apps_or_resources_is_state_only(self):
        with patch("shutil.which", return_value=None):
            self.capture(["apply", "nvis-green-a"])
        self.assertEqual(current_mode(), "nvis-green-a")
        self.assertEqual(state_store().planner().manifest.resources, {})
        self.assertFalse((self.home / "data").exists())
        self.assertFalse((self.home / "config with spaces").exists())

    def test_switches_are_backed_up_and_idempotent(self):
        self.capture(["apply", "aviation-red"])
        before = self.tree()
        self.capture(["apply", "aviation-red"])
        self.assertEqual(self.tree(), before)
        output = self.capture(["apply", "nvis-green-a"])
        backup_id = next(line[8:] for line in output.splitlines() if line.startswith("Backup: "))
        prior = json.loads(state_store().backups.read_blob(backup_id, 0))
        self.assertEqual(prior["mode"], "aviation-red")
        self.assertEqual(current_mode(), "nvis-green-a")

    def test_dry_runs_never_create_state_resources_or_processes(self):
        for args in (["apply", "aviation-red", "--dry-run"], ["restore", "--dry-run"],
                     ["uninstall", "--dry-run"]):
            with self.subTest(args=args):
                before = self.tree()
                with patch("subprocess.run", side_effect=AssertionError("spawned")):
                    self.capture(args)
                self.assertEqual(self.tree(), before)
        self.installed()
        self.capture(["apply", "nvis-green-a"])
        before = self.tree()
        self.capture(["restore", "--dry-run"])
        self.capture(["uninstall", "--dry-run"])
        self.assertEqual(self.tree(), before)

    def test_install_after_apply_preserves_active_mode(self):
        self.capture(["apply", "nvis-green-a"])
        self.installed()
        self.assertEqual(current_mode(), "nvis-green-a")

    def test_restore_changes_only_mode_even_when_generated_files_are_modified(self):
        self.installed()
        self.capture(["apply", "aviation-red"])
        target = HtopAdapter().targets["aviation-red"]
        target.write_bytes(target.read_bytes() + b"# edited after install\n")
        before = {p: p.read_bytes() for p in self.home.rglob("*") if p.is_file()
                  and not p.is_relative_to(state_store().paths.state)}
        self.capture(["restore"])
        self.assertEqual(current_mode(), "original")
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)
        with self.assertRaises(ConflictError):
            uninstall_plan()

    def test_complete_cycle_restores_personal_bytes_and_retains_backups_and_code_profiles(self):
        original = self.installed()
        code_files = self.prepared_code()
        self.capture(["apply", "aviation-red"])
        self.capture(["apply", "nvis-green-a"])
        self.capture(["restore"])
        self.capture(["uninstall"])
        self.assertEqual(current_mode(), "original")
        self.assertEqual(state_store().planner().manifest.resources, {})
        for path, data in {**original, **code_files}.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertTrue(state_store().backups.list())
        before = self.tree()
        self.capture(["uninstall"])
        self.capture(["restore"])
        self.assertEqual(self.tree(), before)

    def test_implicit_wrappers_follow_mode_and_normal_wrappers_return_after_restore(self):
        self.installed()
        self.prepared_code()
        for palette in ("aviation-red", "nvis-green-a"):
            self.capture(["apply", palette])
            for app in ("terminator", "htop", "vim", "code"):
                argv = json.loads(self.capture(["open", app, "--dry-run"]))
                command = argv["argv"] if isinstance(argv, dict) else argv
                if app == "htop":
                    self.assertIn(palette, argv["env"]["HTOPRC"])
                elif app == "vim":
                    self.assertIn("aeronox_red" if palette == "aviation-red" else "aeronox_green",
                                  command[2])
                elif app == "code":
                    self.assertIn(PROFILE_NAMES[palette], command)
                else:
                    self.assertIn("AeroNox Aviation Red" if palette == "aviation-red"
                                  else "AeroNox NVIS Green A", command)
        self.capture(["restore"])
        for app in ("terminator", "htop", "vim"):
            self.assertEqual(json.loads(self.capture(["open", app, "--dry-run"])),
                             [f"/synthetic/{app}"])
        self.assertEqual(json.loads(self.capture(["open", "code", "--palette", "original",
                                                  "--dry-run"])), ["/synthetic/code"])

    def test_uninstall_does_not_depend_on_application_availability(self):
        original = self.installed()
        self.capture(["apply", "aviation-red"])
        with patch("shutil.which", return_value=None):
            self.capture(["uninstall"])
        for path, data in original.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertEqual(current_mode(), "original")

    def test_conflicts_abort_all_removal_and_mode_changes(self):
        self.installed()
        self.capture(["apply", "aviation-red"])
        modified = VimAdapter().targets["aviation-red"]
        modified.write_bytes(modified.read_bytes() + b'" personal changes\n')
        before = self.tree()
        for dry_run in (False, True):
            args = ["uninstall", "--dry-run"] if dry_run else ["uninstall"]
            error = io.StringIO()
            with redirect_stderr(error), self.assertRaises(SystemExit) as result:
                main(args)
            self.assertEqual(result.exception.code, 1)
            self.assertIn("no changes made", error.getvalue())
            self.assertEqual(self.tree(), before)
        self.assertEqual(current_mode(), "aviation-red")

    def test_uninstall_preserves_personal_terminator_changes_since_install(self):
        original = self.installed()
        path = TerminatorAdapter().config_path
        changed = path.read_bytes().replace(b"focus = sloppy", b"focus = click")
        path.write_bytes(changed)
        self.capture(["uninstall"])
        self.assertEqual(path.read_bytes(),
                         original[path].replace(b"focus = sloppy", b"focus = click"))

    def test_unknown_or_old_location_ownership_is_preserved_not_deleted(self):
        self.installed()
        path = self.home / "old data/unrecognized.vim"
        path.parent.mkdir()
        path.write_bytes(b"personal or old-version resource")
        store = state_store()
        manifest = store.planner().manifest
        resources = dict(manifest.resources)
        resources[str(path)] = Resource(digest(path.read_bytes()), 0o600, "vim", "generated")
        state = replace(manifest, resources=MappingProxyType(resources)).serialize()
        store.state.write_bytes(state)
        before = self.tree()
        with self.assertRaisesRegex(ConflictError, "ownership record"):
            uninstall_plan()
        self.assertEqual(self.tree(), before)

    def test_atomic_uninstall_failure_rolls_back_every_component_and_mode(self):
        self.installed()
        self.capture(["apply", "nvis-green-a"])
        store, plan = uninstall_plan()
        paths = tuple(change.path for change in plan.changes) + (store.state,)
        before = {p: p.read_bytes() for p in paths}
        replace_file = store.files.replace

        def fail(path, *args, **kwargs):
            if path == store.state:
                raise OSError("Injected final state failure")
            return replace_file(path, *args, **kwargs)

        with patch.object(store.files, "replace", side_effect=fail):
            with self.assertRaises(TransactionError) as result:
                store.execute(plan)
        self.assertEqual(result.exception.conflicts, ())
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertEqual(current_mode(), "nvis-green-a")

    def test_concurrent_state_edits_abort_a_reviewed_mode_plan(self):
        self.capture(["apply", "aviation-red"])
        store, plan = mode_plan("nvis-green-a")
        store.state.write_bytes(store.state.read_bytes() + b"\n")
        before = self.tree()
        with self.assertRaises(ConflictError):
            store.execute(plan)
        self.assertEqual(self.tree(), before)

    def test_concurrent_resource_edits_abort_reviewed_uninstall_before_mutation(self):
        self.installed()
        store, plan = uninstall_plan()
        target = HtopAdapter().targets["nvis-green-a"]
        target.write_bytes(target.read_bytes() + b"sort_key=20\n")
        before = self.tree()
        with self.assertRaises(ConflictError):
            store.execute(plan)
        self.assertEqual(self.tree(), before)

    def test_forged_state_modes_cannot_bypass_validation(self):
        store, plan = mode_plan("aviation-red")
        for bad in (replace(plan, mode_change=None),
                    replace(plan, mode_change="unknown"),
                    replace(plan, manifest=replace(plan.manifest, mode="nvis-green-a"))):
            with self.assertRaises(SafetyError):
                store.execute(bad)
        self.assertEqual(self.tree(), {})

    def test_mode_write_failure_preserves_previous_mode_and_journals_rollback(self):
        self.capture(["apply", "aviation-red"])
        store, plan = mode_plan("nvis-green-a")
        replace_file = store.files.replace

        def fail(path, *args, **kwargs):
            if path == store.state:
                raise OSError("Injected state write failure")
            return replace_file(path, *args, **kwargs)

        with patch.object(store.files, "replace", side_effect=fail):
            with self.assertRaises(TransactionError) as result:
                store.execute(plan)
        self.assertEqual(current_mode(), "aviation-red")
        self.assertEqual(store.backups.inspect(result.exception.backup_id)["status"], "rolled_back")

    def test_corrupt_or_symlink_state_is_never_replaced_by_restore(self):
        store = state_store()
        store.files.private_directory(store.paths.state, create=True)
        store.state.write_bytes(b"{invalid state")
        store.state.chmod(0o600)
        with self.assertRaises(SafetyError):
            mode_plan("original")
        self.assertEqual(store.state.read_bytes(), b"{invalid state")
        store.state.unlink()
        target = self.home / "personal.json"
        target.write_bytes(b"personal")
        store.state.symlink_to(target)
        with self.assertRaises(SafetyError):
            mode_plan("original")
        self.assertEqual(target.read_bytes(), b"personal")

    def test_legacy_state_migrates_only_on_actual_mode_change(self):
        store = state_store()
        store.files.private_directory(store.paths.state, create=True)
        old = b'{"schema_version":1,"mode":"original","resources":{}}'
        store.state.write_bytes(old)
        store.state.chmod(0o600)
        self.capture(["restore"])
        self.assertEqual(store.state.read_bytes(), old)
        self.capture(["apply", "aviation-red", "--dry-run"])
        self.assertEqual(store.state.read_bytes(), old)
        self.capture(["apply", "aviation-red"])
        self.assertEqual(json.loads(store.state.read_bytes())["schema_version"], 2)

    def test_doctor_paths_are_opt_in_and_version_output_is_filtered(self):
        self.assertNotIn(str(self.home), self.capture(["doctor"]))
        self.assertIn(str(self.home), self.capture(["doctor", "--paths"]))
        result = subprocess.CompletedProcess([], 0, "VIM - Vi IMproved 9.1\nSYNTHETIC_SECRET", "")
        with patch("aeronox.commands.subprocess.run", return_value=result) as run:
            output = self.capture(["doctor", "--versions"])
        self.assertIn("9.1", output)
        self.assertNotIn("SYNTHETIC_SECRET", output)
        self.assertEqual(run.call_count, 4)
        for call in run.call_args_list:
            self.assertEqual(call.args[0][-1], "--version")
            self.assertEqual(call.kwargs["timeout"], 3)
            self.assertNotIn("shell", call.kwargs)

    def test_doctor_version_timeouts_and_private_output_are_not_logged(self):
        with patch("aeronox.commands.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(["synthetic"], 3)):
            output = self.capture(["doctor", "--versions"])
        self.assertIn("unavailable", output)
        result = subprocess.CompletedProcess([], 0, "SYNTHETIC_PRIVATE_OUTPUT", "PRIVATE_ERROR")
        with patch("aeronox.commands.subprocess.run", return_value=result):
            output = self.capture(["doctor", "--versions"])
        self.assertNotIn("PRIVATE", output)



    def test_pre_epoch_source_timestamp_is_preserved_in_snapshot(self):
        self.fixtures()
        source = TerminatorAdapter().config_path
        os.utime(source, ns=(-1_000_000_000, -1_000_000_000))
        original = source.read_bytes()
        adapter = TerminatorAdapter()
        result = adapter.install(adapter.plan_install(PaletteCatalog()))
        journal = adapter.store.backups.inspect(result.backup_id)
        self.assertEqual(journal["entries"][0]["before"]["mtime_ns"], -1_000_000_000)
        self.assertEqual(adapter.store.backups.read_blob(result.backup_id, 0), original)


if __name__ == "__main__":
    unittest.main()
