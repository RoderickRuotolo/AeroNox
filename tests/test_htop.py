"""Separate copies and isolated ncurses smoke tests; no real dotfiles are used."""

import fcntl
import io
import json
import os
import pty
import select
import shutil
import struct
import subprocess
import tempfile
import termios
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from aeronox.adapters.htop import HtopAdapter, monochrome_config
from aeronox.catalog import PaletteCatalog
from aeronox.cli import main
from aeronox.models import PALETTE_IDS
from aeronox.storage import ConflictError, SafetyError
from aeronox.transactions import TransactionError

NATIVE_HTOP = shutil.which("htop")
FIXTURE = Path(__file__).parent / "fixtures/htop/custom.htoprc"


class HtopTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aeronox htop ")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / "home with spaces"
        self.home.mkdir(mode=0o700)
        environment = patch.dict(os.environ, {
            "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "config"),
            "XDG_STATE_HOME": str(self.home / "state"), "XDG_DATA_HOME": str(self.home / "data"),
            "HTOPRC": "",
        })
        environment.start()
        self.addCleanup(environment.stop)
        detection = patch("aeronox.adapters.generated.shutil.which", return_value="/synthetic/htop")
        detection.start()
        self.addCleanup(detection.stop)
        self.adapter = HtopAdapter()
        self.catalog = PaletteCatalog()

    def source(self, content=None):
        content = FIXTURE.read_bytes() if content is None else content
        self.adapter.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.adapter.config_path.write_bytes(content)
        return content

    def install(self):
        return self.adapter.install(self.adapter.plan_install(self.catalog))

    def tree(self):
        return {str(p.relative_to(self.home)): p.read_bytes() if p.is_file() else None
                for p in self.home.rglob("*")}

    def test_generated_copies_preserve_preferences_and_original(self):
        original = self.source()
        result = self.install()
        self.assertTrue(result.changed)
        self.assertEqual(self.adapter.config_path.read_bytes(), original)
        expected = original.replace(b"color_scheme=6", b"color_scheme=1")
        for path in self.adapter.targets.values():
            self.assertEqual(path.read_bytes(), expected)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertTrue(self.adapter.verify().ok)

    def test_new_user_uses_minimal_monochrome_defaults(self):
        self.install()
        self.assertFalse(self.adapter.config_path.exists())
        for path in self.adapter.targets.values():
            self.assertEqual(path.read_bytes(), b"color_scheme=1\n")

    def test_legacy_fallback_is_copied_without_migration_or_deletion(self):
        legacy = self.home / ".htoprc"
        original = FIXTURE.read_bytes()
        legacy.write_bytes(original)
        self.install()
        self.assertEqual(legacy.read_bytes(), original)
        self.assertFalse(self.adapter.config_path.exists())
        self.assertIn(b"sort_key=46", self.adapter.targets["aviation-red"].read_bytes())

    def test_xdg_source_takes_precedence_over_legacy(self):
        self.source(b"sort_key=46\n")
        (self.home / ".htoprc").write_bytes(b"sort_key=1\n")
        self.install()
        self.assertIn(b"sort_key=46", self.adapter.targets["aviation-red"].read_bytes())

    def test_explicit_htoprc_is_copied_and_parent_environment_unchanged(self):
        explicit = self.home / "custom htoprc"
        explicit.write_bytes(b"sort_key=20\n")
        with patch.dict(os.environ, HTOPRC=str(explicit)):
            self.install()
            self.assertEqual(os.environ["HTOPRC"], str(explicit))
            self.assertIn(b"sort_key=20", self.adapter.targets["nvis-green-a"].read_bytes())
        self.assertEqual(explicit.read_bytes(), b"sort_key=20\n")

    def test_untrusted_source_paths_are_refused(self):
        for source in ("relative", str(self.home.parent / "outside")):
            with self.subTest(source=source), patch.dict(os.environ, HTOPRC=source):
                with self.assertRaises(SafetyError):
                    self.adapter.plan_install(self.catalog)
        self.assertEqual(self.tree(), {})

    def test_source_symlink_is_refused(self):
        source = self.home / "source"
        source.write_bytes(b"color_scheme=0\n")
        self.adapter.config_path.parent.mkdir(parents=True)
        self.adapter.config_path.symlink_to(source)
        with self.assertRaises(SafetyError):
            self.adapter.plan_install(self.catalog)
        self.assertEqual(source.read_bytes(), b"color_scheme=0\n")

    def test_managed_copy_cannot_be_source(self):
        with patch.dict(os.environ, HTOPRC=str(self.adapter.targets["aviation-red"])):
            with self.assertRaises(SafetyError):
                self.adapter.plan_install(self.catalog)

    def test_transform_preserves_crlf_comments_and_unknown_values(self):
        raw = b"# keep\r\ncolor_scheme = 6 # comment\r\nunknown=\xff\r\n"
        self.assertEqual(monochrome_config(raw),
                         b"# keep\r\ncolor_scheme = 1 # comment\r\nunknown=\xff\r\n")
        self.assertEqual(monochrome_config(b"fields=0 1"), b"fields=0 1\ncolor_scheme=1\n")
        self.assertEqual(monochrome_config(b"color_scheme=6"), b"color_scheme=1")

    def test_ambiguous_or_binary_config_is_refused(self):
        for raw in (b"color_scheme=0\ncolor_scheme=1\n", b"key=\x00\n", b"key=x\r"):
            with self.subTest(raw=raw), self.assertRaises(SafetyError):
                monochrome_config(raw)

    def test_dry_run_does_not_write_or_spawn(self):
        self.source()
        before = self.tree()
        output = io.StringIO()
        with patch("aeronox.commands.subprocess.run", side_effect=AssertionError("spawned")):
            with redirect_stdout(output):
                self.assertEqual(main(["install", "--components", "htop", "--dry-run"]), 0)
        self.assertEqual(self.tree(), before)
        self.assertNotIn("fields=", output.getvalue())
        self.assertIn("htop: two managed resources", output.getvalue())

    def test_reinstall_is_idempotent_and_source_changes_refresh_copies(self):
        self.source()
        self.install()
        before = self.tree()
        self.assertFalse(self.install().changed)
        self.assertEqual(self.tree(), before)
        self.source(b"sort_key=20\ncolor_scheme=2\n")
        result = self.install()
        self.assertTrue(result.changed)
        self.assertIn(b"sort_key=20", self.adapter.targets["aviation-red"].read_bytes())
        self.assertIn(b"sort_key=46", self.adapter.store.backups.read_blob(result.backup_id, 0))

    def test_htop_or_user_rewrite_is_not_overwritten_or_removed(self):
        self.install()
        target = self.adapter.targets["aviation-red"]
        target.write_bytes(target.read_bytes() + b"sort_key=20\n")
        before = self.tree()
        for operation in (lambda: self.adapter.plan_install(self.catalog),
                          self.adapter.plan_uninstall,
                          lambda: self.adapter.open_command("aviation-red", [])):
            with self.assertRaises(ConflictError):
                operation()
        self.assertFalse(self.adapter.verify().ok)
        self.assertEqual(self.tree(), before)

    def test_unmanaged_target_collision_is_preserved(self):
        target = self.adapter.targets["aviation-red"]
        target.parent.mkdir(parents=True)
        target.write_bytes(b"personal resource")
        with self.assertRaises(ConflictError):
            self.adapter.plan_install(self.catalog)
        self.assertEqual(target.read_bytes(), b"personal resource")

    def test_partial_failure_rolls_back_both_copies(self):
        original = self.source()
        plan = self.adapter.plan_install(self.catalog)
        replace_file = self.adapter.store.files.replace
        second = self.adapter.targets["nvis-green-a"]

        def fail(path, *args, **kwargs):
            if path == second:
                raise OSError("Injected failure")
            return replace_file(path, *args, **kwargs)

        with patch.object(self.adapter.store.files, "replace", side_effect=fail):
            with self.assertRaises(TransactionError):
                self.adapter.install(plan)
        self.assertFalse(self.adapter.targets["aviation-red"].exists())
        self.assertFalse(self.adapter.store.state.exists())
        self.assertEqual(self.adapter.config_path.read_bytes(), original)

    def test_uninstall_removes_only_owned_copies(self):
        original = self.source()
        self.install()
        self.adapter.store.execute(self.adapter.plan_uninstall())
        self.assertEqual(self.adapter.config_path.read_bytes(), original)
        self.assertTrue(all(not p.exists() for p in self.adapter.targets.values()))
        self.assertEqual(self.adapter.plan_uninstall().changes, ())

    def test_launcher_uses_copy_and_native_monochrome(self):
        self.install()
        for palette in PALETTE_IDS:
            args = ["--filter", "text with spaces; $(literal)"]
            self.assertEqual(self.adapter.open_command(palette, args),
                             ["/synthetic/htop", "-C", *args])
            delta = self.adapter.launch_environment(palette)
            self.assertEqual(delta["HTOPRC"], str(self.adapter.targets[palette]))
            self.assertTrue(Path(delta["XDG_STATE_HOME"]).is_relative_to(self.adapter.paths.state))
        self.assertEqual(self.adapter.open_command("original", []), ["/synthetic/htop"])
        self.assertEqual(self.adapter.launch_environment("original"), {})

    def test_missing_integration_has_actionable_diagnostic(self):
        with self.assertRaisesRegex(ConflictError, "install --components htop"):
            self.adapter.open_command("aviation-red", [])

    def test_history_directory_symlink_is_refused_before_launch(self):
        self.install()
        outside = self.home.parent / "outside state"
        outside.mkdir()
        (self.adapter.paths.state / "htop").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(SafetyError):
            self.adapter.launch_environment("aviation-red")
        self.assertEqual(list(outside.iterdir()), [])

    def test_cli_dry_run_reports_only_environment_delta(self):
        self.install()
        before = self.tree()
        output = io.StringIO()
        with patch.dict(os.environ, AERONOX_TEST_SECRET="never print me"):
            with redirect_stdout(output):
                self.assertEqual(main(["open", "htop", "--palette", "aviation-red",
                                       "--dry-run"]), 0)
        launch = json.loads(output.getvalue())
        self.assertEqual(launch["argv"], ["/synthetic/htop", "-C"])
        self.assertEqual(set(launch["env"]), {"HTOPRC", "XDG_STATE_HOME"})
        self.assertNotIn("never print me", output.getvalue())
        self.assertEqual(self.tree(), before)

    def test_cli_passes_child_environment_without_mutating_parent(self):
        self.install()
        before = dict(os.environ)
        with patch("aeronox.commands.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 4)) as run:
            self.assertEqual(main(["open", "htop", "--palette", "nvis-green-a",
                                   "--", "--filter", "literal ; text"]), 4)
        self.assertEqual(dict(os.environ), before)
        self.assertEqual(run.call_args.args[0],
                         ["/synthetic/htop", "-C", "--filter", "literal ; text"])
        self.assertEqual(run.call_args.kwargs["env"]["HTOPRC"],
                         str(self.adapter.targets["nvis-green-a"]))
        self.assertNotIn("shell", run.call_args.kwargs)

    @unittest.skipUnless(NATIVE_HTOP, "Native htop not installed")
    def test_native_htop_controls_render_in_isolated_pty_for_both_palettes(self):
        original = self.source()
        self.install()
        for palette in PALETTE_IDS:
            with self.subTest(palette=palette):
                with patch("aeronox.adapters.generated.shutil.which", return_value=NATIVE_HTOP):
                    command = self.adapter.open_command(palette, ["-p", str(os.getpid())])
                    delta = self.adapter.launch_environment(palette)
                env = {**os.environ, **delta, "TERM": "xterm-256color", "LC_ALL": "C"}
                master, slave = pty.openpty()
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 36, 120, 0, 0))
                process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave,
                                           env=env, cwd=self.home, start_new_session=True)
                os.close(slave)
                output = bytearray()
                try:
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        readable, _, _ = select.select([master], [], [], 0.1)
                        if readable:
                            try:
                                output.extend(os.read(master, 65536))
                            except OSError:
                                break
                        if b"Quit" in output:
                            break
                    os.write(master, b"q")
                    process.wait(timeout=5)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
                    os.close(master)
                self.assertEqual(process.returncode, 0, "htop failed in temporary PTY")
                for label in (b"Help", b"Setup", b"Quit"):
                    self.assertTrue(label in output, "A main htop control was not rendered")
                self.assertEqual(self.adapter.config_path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
