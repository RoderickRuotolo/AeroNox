"""Multi-adapter CLI behavior with fake executables and temporary HOME/XDG."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from aeronox.adapters.htop import HtopAdapter
from aeronox.adapters.terminator import TerminatorAdapter
from aeronox.adapters.vim import VimAdapter
from aeronox.cli import main


class ApplicationCommandsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aeronox multi adapter ")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        environment = patch.dict(os.environ, {
            "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "config"),
            "XDG_STATE_HOME": str(self.home / "state"), "XDG_DATA_HOME": str(self.home / "data"),
            "HTOPRC": "",
        })
        environment.start()
        self.addCleanup(environment.stop)
        detection = patch("shutil.which", side_effect=lambda name: f"/synthetic/{name}")
        detection.start()
        self.addCleanup(detection.stop)

    def capture(self, args):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(args), 0)
        return output.getvalue()

    def test_combined_install_retains_all_resource_ownership_and_is_idempotent(self):
        output = self.capture(["install"])
        self.assertIn("vscode: pending", output)
        self.assertTrue(TerminatorAdapter().verify().ok)
        self.assertTrue(HtopAdapter().verify().ok)
        self.assertTrue(VimAdapter().verify().ok)
        state = HtopAdapter().store.planner().manifest
        self.assertEqual(len(state.resources), 5)
        self.assertEqual({record.owner for record in state.resources.values()},
                         {"terminator", "htop", "vim"})
        before = {p: p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        self.capture(["install"])
        after = {p: p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        self.assertEqual(after, before)

    def test_combined_dry_run_never_creates_files_or_processes(self):
        with patch("aeronox.commands.subprocess.run", side_effect=AssertionError("spawned")):
            output = self.capture(["install", "--dry-run"])
        for app in ("terminator", "htop", "vim"):
            self.assertIn(app + ":", output)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_partial_failure_reports_committed_component_and_backup(self):
        vim = VimAdapter()
        target = vim.targets["aviation-red"]
        target.parent.mkdir(parents=True)
        target.write_bytes(b'" personal file\n')
        error = io.StringIO()
        with redirect_stderr(error):
            with self.assertRaises(SystemExit) as result:
                main(["install", "--components", "htop,vim"])
        self.assertEqual(result.exception.code, 1)
        self.assertIn("htop: resources installed", error.getvalue())
        self.assertIn("Backup:", error.getvalue())
        self.assertIn("vim: failed", error.getvalue())
        self.assertIn("remain committed", error.getvalue())
        self.assertTrue(HtopAdapter().verify().ok)
        self.assertEqual(target.read_bytes(), b'" personal file\n')
        self.assertFalse(vim.targets["nvis-green-a"].exists())

    def test_original_launches_do_not_require_generated_resources(self):
        for app in ("htop", "vim"):
            output = self.capture(["open", app, "--dry-run", "--", "literal ; argument"])
            self.assertEqual(json.loads(output), [f"/synthetic/{app}", "literal ; argument"])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_installed_cli_passes_htoprc_only_to_fake_child(self):
        binary_dir = self.home / "bin"
        binary_dir.mkdir()
        for name in ("htop", "vim"):
            executable = binary_dir / name
            executable.write_text(
                "#!/usr/bin/python3\nimport json, os, sys\n"
                "print(json.dumps({'args': sys.argv[1:], 'HTOPRC': os.environ.get('HTOPRC')}))\n"
            )
            executable.chmod(0o700)
        env = {**os.environ, "PATH": str(binary_dir) + os.pathsep + os.defpath}

        def cli(*args):
            result = subprocess.run([sys.executable, "-m", "aeronox", *args], env=env,
                                    cwd=self.home, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

        cli("install", "--components", "htop,vim")
        child = json.loads(cli("open", "htop", "--palette", "aviation-red", "--",
                               "--filter", "literal ; data"))
        self.assertEqual(child["args"], ["-C", "--filter", "literal ; data"])
        self.assertEqual(child["HTOPRC"], str(HtopAdapter().targets["aviation-red"]))
        self.assertEqual(os.environ["HTOPRC"], "")
        child = json.loads(cli("open", "vim", "--palette", "nvis-green-a", "--", "my file.md"))
        self.assertEqual(child["args"][0], "-c")
        self.assertIn("colorscheme aeronox_green", child["args"][1])
        self.assertEqual(child["args"][-1], "my file.md")
        self.assertEqual(child["HTOPRC"], "")


if __name__ == "__main__":
    unittest.main()
