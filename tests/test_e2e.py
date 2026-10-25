"""Installed CLI lifecycle with synthetic configs, fake children and temporary HOME/XDG."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aeronox.adapters.htop import HtopAdapter
from aeronox.adapters.terminator import TerminatorAdapter
from aeronox.adapters.vim import VimAdapter
from aeronox.adapters.vscode import VSCodeAdapter
from aeronox.adapters.vscode_theme import PROFILE_NAMES, snippet
from aeronox.catalog import PaletteCatalog

FIXTURES = Path(__file__).parent / "fixtures"


class InstalledE2ETests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aeronox E2E ")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / "home with spaces"
        self.home.mkdir(mode=0o700)
        self.env = {**os.environ, "HOME": str(self.home),
                    "XDG_CONFIG_HOME": str(self.home / "config"),
                    "XDG_STATE_HOME": str(self.home / "state"),
                    "XDG_DATA_HOME": str(self.home / "data"), "HTOPRC": "", "VSCODE_PORTABLE": ""}
        environment = patch.dict(os.environ, self.env)
        environment.start()
        self.addCleanup(environment.stop)
        self.binary = self.home / "bin"
        self.binary.mkdir()
        for app in ("terminator", "htop", "vim", "code"):
            path = self.binary / app
            path.write_text(
                "#!/usr/bin/python3\nimport json,os,sys\n"
                "print(json.dumps({'argv':sys.argv[1:],'HTOPRC':os.environ.get('HTOPRC')}))\n"
            )
            path.chmod(0o700)
        self.env["PATH"] = str(self.binary) + os.pathsep + os.defpath

    def cli(self, *args, expected=0):
        result = subprocess.run([sys.executable, "-m", "aeronox", *args], env=self.env,
                                cwd=self.home, capture_output=True, text=True,
                                timeout=15, check=False)
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def tree(self):
        return {str(p.relative_to(self.home)): p.read_bytes() if p.is_file() else None
                for p in self.home.rglob("*")}

    def personal(self):
        files = {}
        for path, source in (
            (TerminatorAdapter().config_path, FIXTURES / "terminator/complex.conf"),
            (HtopAdapter().config_path, FIXTURES / "htop/custom.htoprc"),
            (self.home / ".vimrc", FIXTURES / "vim/personal.vimrc"),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.read_bytes())
            files[path] = path.read_bytes()
        for name in (".bashrc", ".zshrc"):
            path = self.home / name
            path.write_bytes(b"# synthetic personal preferences\n")
            files[path] = path.read_bytes()
        return files

    def code_profiles(self):
        root = VSCodeAdapter().paths.config.parent / "Code/User"
        registry = root / "globalStorage/storage.json"
        entries = []
        for palette in PaletteCatalog().list():
            profile_id = "synthetic-" + palette.id
            entries.append({"name": PROFILE_NAMES[palette.id], "location": profile_id})
            settings = root / "profiles" / profile_id / "settings.json"
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_bytes(snippet(palette))
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({"userDataProfiles": entries}))
        (root / "settings.json").write_bytes(b'{"personalDefault":"synthetic"}')
        return {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def test_full_installed_lifecycle_keeps_personal_configs_and_manual_profiles(self):
        original = {**self.personal(), **self.code_profiles()}
        before = self.tree()
        self.cli("install", "--dry-run")
        self.assertEqual(self.tree(), before)
        self.cli("install")
        installed = self.tree()
        self.cli("install")
        self.assertEqual(self.tree(), installed)
        for palette in ("aviation-red", "nvis-green-a"):
            before = self.tree()
            self.cli("apply", palette, "--dry-run")
            self.assertEqual(self.tree(), before)
            self.cli("apply", palette)
            self.assertEqual(self.cli("current").stdout.strip(), palette)
            for app in ("terminator", "htop", "vim", "code"):
                child = json.loads(self.cli("open", app).stdout)
                if app == "htop":
                    self.assertIn(palette, child["HTOPRC"])
                    self.assertEqual(child["argv"], ["-C"])
                elif app == "vim":
                    self.assertIn("aeronox_red" if palette == "aviation-red"
                                  else "aeronox_green", child["argv"][1])
                elif app == "code":
                    self.assertIn(PROFILE_NAMES[palette], child["argv"])
                else:
                    self.assertIn("AeroNox Aviation Red" if palette == "aviation-red"
                                  else "AeroNox NVIS Green A", child["argv"])
        self.cli("restore")
        self.assertEqual(self.cli("current").stdout.strip(), "original")
        for app in ("terminator", "htop", "vim"):
            child = json.loads(self.cli("open", app).stdout)
            self.assertEqual(child["argv"], [])
            self.assertEqual(child["HTOPRC"], "")
        self.cli("uninstall", "--dry-run")
        self.cli("uninstall")
        for path, data in original.items():
            self.assertEqual(path.read_bytes(), data)
        for adapter in (HtopAdapter(), VimAdapter(), VSCodeAdapter()):
            self.assertTrue(all(not p.exists() for p in adapter.targets.values()))
        self.assertIn("committed", self.cli("backup", "list").stdout)
        after = self.tree()
        self.cli("uninstall")
        self.assertEqual(self.tree(), after)

    def test_new_user_apps_missing_and_unprepared_code_do_not_touch_default(self):
        self.env["PATH"] = str(self.home / "missing binaries")
        before = self.tree()
        result = self.cli("install")
        self.assertIn("skipped", result.stdout)
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.cli("current").stdout.strip(), "original")
        self.env["PATH"] = str(self.binary)
        before = self.tree()
        result = self.cli("open", "code", expected=1)
        self.assertIn("prepare dedicated profiles", result.stderr)
        self.cli("apply", "aviation-red")
        self.cli("open", "code", expected=1)
        self.assertFalse((self.home / "config/Code").exists())
        self.cli("restore")
        self.cli("uninstall")
        self.assertFalse((self.home / "data").exists())
        self.assertTrue(set(before) <= set(self.tree()))

    def test_changed_resource_blocks_entire_cli_uninstall_and_restore_still_works(self):
        original = self.personal()
        self.cli("install")
        self.cli("apply", "aviation-red")
        changed = HtopAdapter().targets["aviation-red"]
        changed.write_bytes(changed.read_bytes() + b"sort_key=20\n")
        before = self.tree()
        result = self.cli("uninstall", expected=1)
        self.assertIn("no changes made", result.stderr)
        self.assertEqual(self.tree(), before)
        self.cli("restore")
        self.assertTrue(changed.read_bytes().endswith(b"sort_key=20\n"))
        self.assertEqual(self.cli("current").stdout.strip(), "original")
        for path, data in original.items():
            if path != TerminatorAdapter().config_path:
                self.assertEqual(path.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
