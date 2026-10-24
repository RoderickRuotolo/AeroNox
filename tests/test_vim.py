"""Generated Vim resources and actual headless loading in temporary HOME/XDG."""

import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from aeronox.adapters.vim import GROUPS, SCHEME_NAMES, VimAdapter, colorscheme, xterm256
from aeronox.catalog import PaletteCatalog
from aeronox.cli import main
from aeronox.storage import ConflictError, SafetyError
from aeronox.transactions import TransactionError

NATIVE_VIM = shutil.which("vim")
FIXTURE = Path(__file__).parent / "fixtures/vim/personal.vimrc"


class VimTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aeronox vim ")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / "home with spaces"
        self.home.mkdir(mode=0o700)
        environment = patch.dict(os.environ, {
            "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "config"),
            "XDG_STATE_HOME": str(self.home / "state"), "XDG_DATA_HOME": str(self.home / "data"),
            "HTOPRC": "", "VIMINIT": "", "EXINIT": "", "GVIMINIT": "",
        })
        environment.start()
        self.addCleanup(environment.stop)
        detection = patch("aeronox.adapters.generated.shutil.which", return_value="/synthetic/vim")
        detection.start()
        self.addCleanup(detection.stop)
        self.adapter = VimAdapter()
        self.catalog = PaletteCatalog()

    def install(self):
        return self.adapter.install(self.adapter.plan_install(self.catalog))

    def tree(self):
        return {str(p.relative_to(self.home)): p.read_bytes() if p.is_file() else None
                for p in self.home.rglob("*")}

    def test_two_xdg_schemes_leave_personal_vimrc_untouched(self):
        vimrc = self.home / ".vimrc"
        original = FIXTURE.read_bytes()
        vimrc.write_bytes(original)
        self.install()
        self.assertEqual(vimrc.read_bytes(), original)
        self.assertFalse((self.home / ".vim").exists())
        for palette in self.catalog.list():
            target = self.adapter.targets[palette.id]
            self.assertTrue(target.is_relative_to(self.adapter.paths.data))
            self.assertEqual(target.name, SCHEME_NAMES[palette.id] + ".vim")
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(target.read_bytes(), colorscheme(palette))
        self.assertTrue(self.adapter.verify().ok)

    def test_all_required_groups_have_rgb_cterm_and_non_color_error_emphasis(self):
        required = {"Normal", "Comment", "Constant", "String", "Identifier", "Statement",
                    "PreProc", "Type", "Special", "LineNr", "CursorLine", "Visual",
                    "StatusLine", "Search", "ErrorMsg", "WarningMsg", "DiffAdd", "DiffDelete"}
        self.assertTrue(required <= set(GROUPS))
        for palette in self.catalog.list():
            lines = colorscheme(palette).decode().splitlines()
            for group in required:
                line = next(line for line in lines if line.startswith(f"highlight {group} "))
                self.assertIn("guifg=", line)
                self.assertIn("guibg=", line)
                self.assertIn("ctermfg=", line)
                self.assertIn("ctermbg=", line)
            error = next(line for line in lines if line.startswith("highlight ErrorMsg "))
            self.assertIn("bold,reverse", error)
            warning = next(line for line in lines if line.startswith("highlight WarningMsg "))
            self.assertIn("bold,underline", warning)
            normal = next(line for line in lines if line.startswith("highlight Normal "))
            self.assertIn("guifg=" + palette.colors["foreground"], normal)
            self.assertIn("guibg=" + palette.colors["background"], normal)

    def test_xterm_approximations_use_stable_extended_indices(self):
        self.assertEqual(xterm256("#000000"), 16)
        self.assertEqual(xterm256("#FFFFFF"), 231)
        self.assertEqual(xterm256("#FF0000"), 196)
        self.assertEqual(xterm256("#808080"), 244)
        for palette in self.catalog.list():
            for color in palette.colors.values():
                self.assertTrue(16 <= xterm256(color) <= 255)

    def test_install_is_idempotent_including_manifest_and_backups(self):
        self.install()
        before = self.tree()
        result = self.install()
        self.assertFalse(result.changed)
        self.assertIsNone(result.backup_id)
        self.assertEqual(self.tree(), before)

    def test_modified_scheme_is_not_overwritten_or_removed(self):
        self.install()
        path = self.adapter.targets["aviation-red"]
        path.write_bytes(path.read_bytes() + b'" personal customization\n')
        before = self.tree()
        for operation in (lambda: self.adapter.plan_install(self.catalog),
                          self.adapter.plan_uninstall,
                          lambda: self.adapter.open_command("aviation-red", [])):
            with self.assertRaises(ConflictError):
                operation()
        self.assertFalse(self.adapter.verify().ok)
        self.assertEqual(self.tree(), before)

    def test_unmanaged_color_file_and_symlink_are_not_claimed(self):
        path = self.adapter.targets["aviation-red"]
        path.parent.mkdir(parents=True)
        path.write_bytes(b'" personal resource\n')
        with self.assertRaises(ConflictError):
            self.adapter.plan_install(self.catalog)
        self.assertEqual(path.read_bytes(), b'" personal resource\n')
        path.unlink()
        path.symlink_to(self.home / "missing")
        with self.assertRaises(SafetyError):
            self.adapter.plan_install(self.catalog)

    def test_uninstall_only_removes_intact_generated_schemes(self):
        vimrc = self.home / ".vimrc"
        vimrc.write_bytes(FIXTURE.read_bytes())
        self.install()
        self.adapter.store.execute(self.adapter.plan_uninstall())
        self.assertEqual(vimrc.read_bytes(), FIXTURE.read_bytes())
        self.assertTrue(all(not p.exists() for p in self.adapter.targets.values()))
        self.assertEqual(self.adapter.plan_uninstall().changes, ())

    def test_manifest_failure_rolls_back_new_schemes(self):
        plan = self.adapter.plan_install(self.catalog)
        replace_file = self.adapter.store.files.replace

        def fail(path, *args, **kwargs):
            if path == self.adapter.store.state:
                raise OSError("Injected failure")
            return replace_file(path, *args, **kwargs)

        with patch.object(self.adapter.store.files, "replace", side_effect=fail):
            with self.assertRaises(TransactionError):
                self.adapter.install(plan)
        self.assertTrue(all(not p.exists() for p in self.adapter.targets.values()))
        self.assertFalse(self.adapter.store.state.exists())

    def test_dry_run_never_writes_or_spawns(self):
        before = self.tree()
        with patch("aeronox.commands.subprocess.run", side_effect=AssertionError("spawned")):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["install", "--components", "vim", "--dry-run"]), 0)
        self.assertEqual(self.tree(), before)

    def test_original_launch_and_passthrough_arguments_are_unchanged(self):
        args = ["README with spaces.md", "literal ; $(text)"]
        self.assertEqual(self.adapter.open_command("original", args), ["/synthetic/vim", *args])
        self.assertEqual(self.tree(), {})
        self.install()
        command = self.adapter.open_command("aviation-red", args)
        self.assertEqual(command[:2], ["/synthetic/vim", "-c"])
        self.assertIn("colorscheme aeronox_red", command[2])
        self.assertEqual(command[3:], args)
        # User startup settings remain in force for actual launches.
        self.assertNotIn("-u", command)

    def test_missing_integration_has_actionable_diagnostic(self):
        with self.assertRaisesRegex(ConflictError, "install --components vim"):
            self.adapter.open_command("aviation-red", [])

    def test_cli_preview_and_real_launch_use_argument_lists(self):
        self.install()
        output = io.StringIO()
        before = self.tree()
        with redirect_stdout(output):
            self.assertEqual(main(["open", "vim", "--palette", "aviation-red", "--dry-run",
                                   "--", "a file.md"]), 0)
        self.assertEqual(json.loads(output.getvalue())[-1], "a file.md")
        self.assertEqual(self.tree(), before)
        with patch("aeronox.commands.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 3)) as run:
            self.assertEqual(main(["open", "vim", "--palette", "aviation-red",
                                   "--", "a file.md"]), 3)
        self.assertEqual(run.call_args.args[0][-1], "a file.md")
        self.assertEqual(run.call_args.kwargs, {"check": False})

    def test_control_characters_in_runtime_path_are_refused(self):
        with patch.dict(os.environ, XDG_DATA_HOME=str(self.home / "data\ncommand")):
            with self.assertRaises(SafetyError):
                VimAdapter()
        self.assertEqual(self.tree(), {})

    def native_load(self, adapter, palette, truecolor):
        with patch("aeronox.adapters.generated.shutil.which", return_value=NATIVE_VIM):
            command = adapter.open_command(palette.id, [
                "-Nu", "NONE", "-i", "NONE", "-n", "-es", "-T", "xterm-256color",
                "--cmd", "set t_Co=256 " + ("termguicolors" if truecolor else "notermguicolors"),
                "-c", f"call assert_equal('{SCHEME_NAMES[palette.id]}', g:colors_name)",
                "-c", f"call assert_equal('{palette.colors['foreground']}', "
                "synIDattr(hlID('Normal'), 'fg', 'gui'))",
                "-c", f"call assert_equal('{xterm256(palette.colors['foreground'])}', "
                "synIDattr(hlID('Normal'), 'fg', 'cterm'))",
                "-c", "call assert_equal('1', synIDattr(hlID('ErrorMsg'), 'bold', 'cterm'))",
                "-c", "call assert_equal(0, get(g:, 'aeronox_injected', 0))",
                "-c", "if len(v:errors) | cquit | endif", "-c", "qa!",
            ])
        result = subprocess.run(command, cwd=self.home, env=dict(os.environ),
                                capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, "Headless Vim failed to load or verify highlights")

    @unittest.skipUnless(NATIVE_VIM, "Native Vim not installed")
    def test_native_vim_loads_both_palettes_in_truecolor_and_256_colors(self):
        self.install()
        before = self.tree()
        for palette in self.catalog.list():
            for truecolor in (False, True):
                with self.subTest(palette=palette.id, truecolor=truecolor):
                    self.native_load(self.adapter, palette, truecolor)
        self.assertEqual(self.tree(), before)
        self.assertFalse((self.home / ".vimrc").exists())
        self.assertFalse((self.home / ".viminfo").exists())

    @unittest.skipUnless(NATIVE_VIM, "Native Vim not installed")
    def test_native_vim_handles_spaces_commas_quotes_backslashes_and_bars(self):
        data = self.home / "data, comma'quote\\back|pipe"
        with patch.dict(os.environ, XDG_DATA_HOME=str(data)):
            adapter = VimAdapter()
            adapter.install(adapter.plan_install(self.catalog))
            for palette in self.catalog.list():
                self.native_load(adapter, palette, False)
        self.assertFalse((self.home / ".vimrc").exists())

    def test_missing_or_sandboxed_app_is_skipped(self):
        for executable in (None, "/snap/bin/vim", "/var/lib/flatpak/exports/bin/vim"):
            with self.subTest(executable=executable):
                with patch("aeronox.adapters.generated.shutil.which", return_value=executable):
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(main(["install", "--components", "vim"]), 0)
                self.assertEqual(self.tree(), {})


if __name__ == "__main__":
    unittest.main()
