"""Synthetic ConfigObj fixtures and temporary HOME/XDG only; no GUI is launched."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from aeronox.adapters.terminator import TerminatorAdapter
from aeronox.adapters.terminator_config import (
    PROFILE_NAMES,
    TerminatorConfig,
    profile_block,
)
from aeronox.catalog import PaletteCatalog
from aeronox.cli import main
from aeronox.paths import XDGPaths
from aeronox.storage import ConflictError, SafetyError, digest
from aeronox.transactions import TransactionError

FIXTURE = Path(__file__).parent / "fixtures/terminator/complex.conf"
EXECUTABLE = "/synthetic/bin/terminator"


class TerminatorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aeronox terminator ")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / "home with spaces"
        self.home.mkdir(mode=0o700)
        environment = patch.dict(os.environ, {
            "HTOPRC": "", "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / "config with spaces"),
            "XDG_STATE_HOME": str(self.home / "state"), "XDG_DATA_HOME": str(self.home / "data"),
        })
        environment.start()
        self.addCleanup(environment.stop)
        executable = patch("aeronox.adapters.terminator.shutil.which", return_value=EXECUTABLE)
        executable.start()
        self.addCleanup(executable.stop)
        self.paths = XDGPaths.resolve()
        self.adapter = TerminatorAdapter()
        self.path = self.adapter.config_path
        self.catalog = PaletteCatalog()

    def fixture(self, content: bytes | None = None) -> bytes:
        raw = FIXTURE.read_bytes() if content is None else content
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(raw)
        self.path.chmod(0o640)
        return raw

    def install(self):
        return self.adapter.install(self.adapter.plan_install(self.catalog))

    def tree(self):
        return {str(p.relative_to(self.home)): (p.stat().st_mode,
                p.read_bytes() if p.is_file() else None) for p in self.home.rglob("*")}

    def capture(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = main(args)
        return result, out.getvalue(), err.getvalue()

    def test_new_user_has_two_profiles_and_no_created_default(self):
        result = self.install()
        self.assertTrue(result.changed)
        document = TerminatorConfig(self.path.read_bytes())
        self.assertEqual(set(document.parsed["profiles"]), set(PROFILE_NAMES.values()))
        self.assertNotIn("default", document.parsed["profiles"])
        self.assertFalse((self.home / ".vimrc").exists())
        self.assertTrue(self.adapter.verify().ok)

    def test_complex_config_preserves_every_original_byte(self):
        original = self.fixture()
        before = TerminatorConfig(original)
        result = self.install()
        after = TerminatorConfig(self.path.read_bytes())
        self.assertEqual(after.without_managed_profiles(), original)
        for path, span in before.spans.items():
            if path == ("profiles",):
                continue
            after_span = after.spans[path]
            self.assertEqual(original[span.start:span.end],
                             after.content[after_span.start:after_span.end], path)
        self.assertEqual(before.parsed["keybindings"], after.parsed["keybindings"])
        self.assertEqual(before.parsed["layouts"], after.parsed["layouts"])
        self.assertEqual(before.parsed["plugins"], after.parsed["plugins"])
        self.assertEqual(before.parsed["unknown_section"], after.parsed["unknown_section"])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.adapter.store.backups.read_blob(result.backup_id, 0), original)

    def test_clone_preserves_non_color_preferences_and_uses_central_palette(self):
        self.fixture()
        self.install()
        document = TerminatorConfig(self.path.read_bytes())
        base = document.profile("default")
        changed = {"use_theme_colors", "background_type", "foreground_color",
                   "background_color", "palette", "cursor_color", "cursor_color_default"}
        for palette in self.catalog.list():
            clone = document.profile(PROFILE_NAMES[palette.id])
            for key, value in base.items():
                if key not in changed:
                    self.assertEqual(clone[key], value, key)
            self.assertEqual(clone["background_color"], palette.colors["background"])
            self.assertEqual(clone["foreground_color"], palette.colors["foreground"])
            self.assertEqual(clone["palette"].split(":"), list(palette.ansi16))
            self.assertEqual(clone["cursor_color"], palette.colors["cursor"])
            self.assertEqual(clone["background_type"], "solid")
            self.assertEqual(clone["use_theme_colors"], "False")

    def test_quoted_profile_multiline_command_and_modern_cursor(self):
        self.fixture()
        adapter = TerminatorAdapter(base_profile="Personal [quoted] profile")
        adapter.install(adapter.plan_install(self.catalog))
        document = TerminatorConfig(self.path.read_bytes())
        base = document.profile("Personal [quoted] profile")
        for palette in self.catalog.list():
            clone = document.profile(PROFILE_NAMES[palette.id])
            self.assertEqual(clone["font"], base["font"])
            self.assertEqual(clone["custom_command"], base["custom_command"])
            self.assertEqual(clone["cursor_bg_color"], palette.colors["cursor"])
            self.assertEqual(clone["cursor_fg_color"], palette.colors["background"])
            self.assertEqual(clone["cursor_color_default"], "False")
        self.assertNotIn(("not a real section",), document.spans)

    def test_missing_default_uses_built_in_defaults_without_adding_default(self):
        original = self.fixture(b"[profiles]\n  [[personal]]\n    font = Mono 17\n")
        self.install()
        document = TerminatorConfig(self.path.read_bytes())
        self.assertEqual(document.without_managed_profiles(), original)
        self.assertNotIn("default", document.parsed["profiles"])
        self.assertEqual(document.profile("personal")["font"], "Mono 17")

    def test_absent_profiles_section_preserves_existing_sections(self):
        original = self.fixture(b"# Synthetic\n[plugins]\n  [[unknown]]\n    data = keep")
        self.install()
        self.assertTrue(self.path.read_bytes().startswith(original))
        self.assertTrue(self.adapter.verify().ok)

    def test_default_at_eof_without_newline_is_byte_identical(self):
        original = self.fixture(b"[profiles]\n [[default]]\n  font = Mono 13")
        before = TerminatorConfig(original)
        self.install()
        after = TerminatorConfig(self.path.read_bytes())
        span = before.spans[("profiles", "default")]
        new_span = after.spans[("profiles", "default")]
        self.assertEqual(original[span.start:span.end], after.content[new_span.start:new_span.end])
        self.assertEqual(after.without_managed_profiles(), original)

    def test_bom_and_crlf_preserved(self):
        original = self.fixture(
            b'\xef\xbb\xbf[profiles]\r\n  [[default]]\r\n    font = Mono 14\r\n'
        )
        self.install()
        raw = self.path.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        self.assertEqual(TerminatorConfig(raw).without_managed_profiles(), original)

    def test_dry_run_never_creates_directories_backups_or_processes(self):
        before = self.tree()
        with patch("aeronox.commands.subprocess.run", side_effect=AssertionError("launched")):
            status, output, _ = self.capture(["install", "--dry-run", "--components", "terminator"])
        self.assertEqual(status, 0)
        self.assertIn(str(self.path), output)
        self.assertIn("two dedicated profiles", output)
        self.assertEqual(self.tree(), before)

    def test_preview_redacts_commands_and_plugin_values(self):
        self.fixture()
        before = self.tree()
        status, output, _ = self.capture(["install", "--dry-run", "--components", "terminator"])
        self.assertEqual(status, 0)
        self.assertNotIn("SYNTHETIC#COMMAND", output)
        self.assertNotIn("SYNTHETIC_NOT_A_SECRET", output)
        self.assertEqual(self.tree(), before)

    def test_install_is_idempotent_including_backups(self):
        self.fixture()
        self.install()
        before = self.tree()
        second = self.install()
        self.assertFalse(second.changed)
        self.assertIsNone(second.backup_id)
        self.assertEqual(self.tree(), before)
        self.assertEqual(len(TerminatorConfig(self.path.read_bytes()).managed_sections()), 2)

    def test_unmanaged_same_name_profile_is_never_overwritten(self):
        for name in PROFILE_NAMES.values():
            with self.subTest(name=name):
                self.fixture(f"[profiles]\n [[{name}]]\n  font = Personal 21\n".encode())
                before = self.tree()
                with self.assertRaises(ConflictError):
                    self.adapter.plan_install(self.catalog)
                self.assertEqual(self.tree(), before)

    def test_profile_scalar_name_collision_is_refused(self):
        self.fixture(b'[profiles]\n "AeroNox Aviation Red" = personal\n')
        with self.assertRaises(SafetyError):
            self.adapter.plan_install(self.catalog)

    def test_user_modified_generated_profile_is_preserved(self):
        self.fixture()
        self.install()
        self.path.write_bytes(self.path.read_bytes().replace(b'"#CC3333"', b'"#AA5555"'))
        before = self.tree()
        with self.assertRaises(ConflictError):
            self.adapter.plan_install(self.catalog)
        with self.assertRaises(ConflictError):
            self.adapter.plan_uninstall()
        self.assertFalse(self.adapter.verify().ok)
        self.assertEqual(self.tree(), before)

    def test_unrelated_personal_edit_does_not_block_reinstallation(self):
        self.fixture()
        self.install()
        raw = self.path.read_bytes().replace(b"focus = sloppy", b"focus = click")
        self.path.write_bytes(raw)
        before = self.tree()
        self.assertFalse(self.install().changed)
        self.assertEqual(self.tree(), before)
        self.assertTrue(self.adapter.verify().ok)

    def test_base_font_change_updates_only_generated_profiles(self):
        self.fixture()
        self.install()
        document = TerminatorConfig(self.path.read_bytes())
        span = document.spans[("profiles", "default")]
        raw = document.content[:span.start] + document.content[span.start:span.end].replace(
            b"Monospace 13", b"Monospace 19") + document.content[span.end:]
        self.path.write_bytes(raw)
        before_default = TerminatorConfig(raw).profile("default")
        result = self.install()
        self.assertTrue(result.changed)
        after = TerminatorConfig(self.path.read_bytes())
        self.assertEqual(after.profile("default"), before_default)
        for name in PROFILE_NAMES.values():
            self.assertEqual(after.profile(name)["font"], "Monospace 19")
        self.assertEqual(self.adapter.store.backups.read_blob(result.backup_id, 0), raw)

    def test_removing_or_renaming_owned_profile_is_a_conflict(self):
        self.install()
        self.path.write_bytes(self.path.read_bytes().replace(b"AeroNox Aviation Red", b"Personal"))
        with self.assertRaises(ConflictError):
            self.adapter.plan_install(self.catalog)
        with self.assertRaises(ConflictError):
            self.adapter.plan_uninstall()

    def test_section_only_uninstall_preserves_personal_edits_and_releases_ownership(self):
        original = self.fixture()
        self.install()
        original_edited = original.replace(b"focus = sloppy", b"focus = click")
        self.path.write_bytes(self.path.read_bytes().replace(b"focus = sloppy", b"focus = click"))
        plan = self.adapter.plan_uninstall()
        self.adapter.store.execute(plan)
        self.assertEqual(self.path.read_bytes(), original_edited)
        self.assertNotIn(str(self.path), self.adapter.store.planner().manifest.resources)
        self.assertFalse(self.adapter.verify().ok)
        self.assertEqual(self.adapter.plan_uninstall().changes, ())

    def test_uninstall_new_file_keeps_shared_config_instead_of_deleting_it(self):
        self.install()
        self.adapter.store.execute(self.adapter.plan_uninstall())
        self.assertTrue(self.path.exists())
        self.assertEqual(TerminatorConfig(self.path.read_bytes()).managed_sections(), {})

    def test_uninstall_does_not_claim_unmanaged_profiles(self):
        self.fixture(b"[profiles]\n [[AeroNox Aviation Red]]\n  font = Personal 20\n")
        before = self.tree()
        self.assertEqual(self.adapter.plan_uninstall().changes, ())
        self.assertEqual(self.tree(), before)

    def test_invalid_duplicate_or_non_utf8_configs_fail_without_content_in_errors(self):
        invalid = [b"[profiles]\n [[default]]\n SYNTHETIC_PRIVATE_INVALID\n",
                   b"[profiles]\n [[default]]\n [[default]]\n", b"[profiles]\n\xff\n",
                   b"profiles = string\n", b"[profiles]\n x = \x00\n"]
        for content in invalid:
            with self.subTest(content=content):
                self.fixture(content)
                before = self.tree()
                with self.assertRaises(SafetyError) as result:
                    self.adapter.plan_install(self.catalog)
                self.assertNotIn("SYNTHETIC_PRIVATE_INVALID", str(result.exception))
                self.assertEqual(self.tree(), before)

    def test_symlink_config_or_parent_is_refused(self):
        outside = self.home / "synthetic-original"
        outside.write_bytes(b"[profiles]\n [[default]]\n")
        self.path.parent.mkdir(parents=True)
        self.path.symlink_to(outside)
        with self.assertRaises(SafetyError):
            self.adapter.plan_install(self.catalog)
        self.path.unlink()
        self.path.parent.rmdir()
        self.path.parent.symlink_to(self.home, target_is_directory=True)
        with self.assertRaises(SafetyError):
            self.adapter.plan_install(self.catalog)
        self.assertEqual(outside.read_bytes(), b"[profiles]\n [[default]]\n")

    def test_concurrent_edit_after_plan_is_not_overwritten(self):
        self.fixture()
        plan = self.adapter.plan_install(self.catalog)
        self.path.write_bytes(self.path.read_bytes() + b"# concurrent edit\n")
        before = self.tree()
        with self.assertRaises(ConflictError):
            self.adapter.install(plan)
        self.assertEqual(self.tree(), before)

    def test_concurrent_edit_during_rendering_is_not_adopted(self):
        self.fixture()
        original_read = self.adapter.store.files.read
        reads = []

        def concurrent_read(path):
            if path == self.path:
                reads.append(path)
                if len(reads) == 2:
                    self.path.write_bytes(self.path.read_bytes() + b"# personal concurrent edit\n")
            return original_read(path)

        with patch.object(self.adapter.store.files, "read", side_effect=concurrent_read):
            with self.assertRaises(ConflictError):
                self.adapter.plan_install(self.catalog)
        self.assertTrue(self.path.read_bytes().endswith(b"# personal concurrent edit\n"))
        self.assertFalse(self.paths.state.exists())

    def test_manifest_failure_rolls_back_entire_shared_config(self):
        original = self.fixture()
        plan = self.adapter.plan_install(self.catalog)
        replace_file = self.adapter.store.files.replace

        def failure(path, *args, **kwargs):
            if path == self.adapter.store.state:
                raise OSError("Injected manifest failure")
            return replace_file(path, *args, **kwargs)

        with patch.object(self.adapter.store.files, "replace", side_effect=failure):
            with self.assertRaises(TransactionError) as result:
                self.adapter.install(plan)
        self.assertEqual(result.exception.conflicts, ())
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(self.adapter.store.state.exists())
        self.assertEqual(self.adapter.store.backups.read_blob(result.exception.backup_id, 0),
                         original)

    def test_missing_app_is_skipped_without_creating_resources(self):
        before = self.tree()
        with patch("aeronox.adapters.terminator.shutil.which", return_value=None):
            status, output, _ = self.capture(["install"])
        self.assertEqual(status, 0)
        self.assertIn("terminator: skipped", output)
        self.assertIn("htop: skipped", output)
        self.assertEqual(self.tree(), before)

    def test_sandboxed_edition_is_skipped(self):
        for executable in ("/snap/bin/terminator", "/var/lib/flatpak/exports/bin/terminator"):
            with self.subTest(executable=executable):
                with patch("aeronox.adapters.terminator.shutil.which", return_value=executable):
                    status, output, _ = self.capture(["install", "--components", "terminator"])
                self.assertEqual(status, 0)
                self.assertIn("manual setup required", output)
                self.assertEqual(self.tree(), {})

    def test_base_profile_selection_and_missing_base(self):
        self.fixture()
        status, _, _ = self.capture(["install", "--components", "terminator", "--base-profile",
                                     "Personal [quoted] profile"])
        self.assertEqual(status, 0)
        document = TerminatorConfig(self.path.read_bytes())
        self.assertEqual(document.profile(PROFILE_NAMES["aviation-red"])["font"], "Monospace 15")
        with self.assertRaises(SafetyError):
            TerminatorAdapter(base_profile="missing").plan_install(self.catalog)
        with self.assertRaises(SafetyError):
            TerminatorAdapter(base_profile="AeroNox Aviation Red")

    def test_profile_argv_is_verified_and_arguments_remain_separate(self):
        self.install()
        args = ["--working-directory", "/tmp/path with spaces", "-x", "printf", "$(touch bad)", ";"]
        for palette_id, name in PROFILE_NAMES.items():
            argv = self.adapter.open_command(palette_id, args)
            self.assertEqual(argv[:6], [EXECUTABLE, "--no-dbus", "--config", str(self.path),
                                       "--profile", name])
            self.assertEqual(argv[6:], args)

    def test_original_mode_opens_normally_without_profiles(self):
        self.assertEqual(self.adapter.open_command("original", ["--new-tab"]),
                         [EXECUTABLE, "--new-tab"])
        self.assertEqual(self.tree(), {})

    def test_missing_install_or_modified_profile_blocks_themed_open(self):
        with self.assertRaises(ConflictError):
            self.adapter.open_command("aviation-red", [])
        self.install()
        self.path.write_bytes(self.path.read_bytes().replace(b'"#CC3333"', b'"#AA5555"'))
        with self.assertRaises(ConflictError):
            self.adapter.open_command("aviation-red", [])

    def test_open_cli_dry_run_does_not_launch_or_write_active_mode(self):
        self.install()
        before = self.tree()
        with patch("aeronox.commands.subprocess.run", side_effect=AssertionError("launched")):
            status, output, _ = self.capture([
                "open", "terminator", "--palette", "nvis-green-a", "--dry-run", "--",
                "--working-directory", "/tmp/with spaces",
            ])
        self.assertEqual(status, 0)
        argv = json.loads(output)
        self.assertIn(PROFILE_NAMES["nvis-green-a"], argv)
        self.assertEqual(argv[-2:], ["--working-directory", "/tmp/with spaces"])
        self.assertEqual(self.tree(), before)

    def test_open_cli_uses_subprocess_list_and_propagates_exit_code(self):
        args = ["open", "terminator", "--", "--working-directory", "/tmp/path with spaces"]
        with patch("aeronox.commands.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 7)) as run:
            self.assertEqual(main(args), 7)
        run.assert_called_once_with([EXECUTABLE, "--working-directory", "/tmp/path with spaces"],
                                    check=False)

    def test_open_uses_active_mode_when_available(self):
        self.install()
        state = self.adapter.store.state
        data = json.loads(state.read_bytes())
        data["mode"] = "aviation-red"
        state.write_text(json.dumps(data))
        status, output, _ = self.capture(["open", "terminator", "--dry-run"])
        self.assertEqual(status, 0)
        self.assertIn(PROFILE_NAMES["aviation-red"], json.loads(output))

    def test_manifest_tracks_only_the_two_owned_profile_hashes(self):
        self.fixture()
        self.install()
        resource = self.adapter.store.planner().manifest.resources[str(self.path)]
        self.assertEqual(resource.ownership, "shared")
        self.assertEqual(set(dict(resource.sections)), set(PROFILE_NAMES.values()))
        document = TerminatorConfig(self.path.read_bytes())
        self.assertEqual(dict(resource.sections),
                         {name: digest(value)
                          for name, value in document.managed_sections().items()})

    def test_forged_section_claim_cannot_claim_default(self):
        self.fixture()
        plan = self.adapter.plan_install(self.catalog)
        item = plan.changes[0]
        forged = replace(item, sections=(("default", digest(b"arbitrary")),))
        with self.assertRaises(SafetyError):
            self.adapter.store.execute(replace(plan, changes=(forged,)))
        self.assertFalse(self.paths.state.exists())

    def test_color_generation_is_semantically_valid_without_unsupported_cursor_key(self):
        for palette in self.catalog.list():
            raw = b"[profiles]\n" + profile_block({"font": "Mono 14"}, palette, b"\n")
            profile = TerminatorConfig(raw).profile(PROFILE_NAMES[palette.id])
            self.assertNotIn("cursor_color", profile)
            self.assertNotIn("cursor_color_default", profile)
            self.assertEqual(len(profile["palette"].split(":")), 16)


    def test_v1_manifest_is_read_and_migrated_only_on_real_install(self):
        self.fixture()
        state = self.adapter.store.state
        state.parent.mkdir(parents=True, mode=0o700)
        old = b'{"schema_version": 1, "mode": "nvis-green-a", "resources": {}}'
        state.write_bytes(old)
        state.chmod(0o600)
        plan = self.adapter.plan_install(self.catalog)
        self.adapter.store.execute(plan, dry_run=True)
        self.assertEqual(state.read_bytes(), old)
        result = self.adapter.install(plan)
        current = json.loads(state.read_bytes())
        self.assertEqual(current["schema_version"], 2)
        self.assertEqual(current["mode"], "nvis-green-a")
        self.assertEqual(self.adapter.store.backups.read_blob(result.backup_id, 1), old)

    def test_unknown_manifest_version_and_invalid_section_hashes_are_refused(self):
        self.install()
        state = self.adapter.store.state
        valid = json.loads(state.read_bytes())
        for scenario in ("version", "hash", "missing", "generated"):
            data = json.loads(json.dumps(valid))
            resource = data["resources"][str(self.path)]
            if scenario == "version":
                data["schema_version"] = 99
            elif scenario == "hash":
                resource["sections"]["AeroNox Aviation Red"] = "invalid hash"
            elif scenario == "missing":
                del resource["sections"]
            else:
                resource["ownership"] = "generated"
            state.write_text(json.dumps(data))
            with self.subTest(scenario=scenario), self.assertRaises(SafetyError):
                self.adapter.plan_install(self.catalog)

    def test_unregistered_reader_cannot_apply_section_plan(self):
        from aeronox.transactions import TransactionStore

        self.fixture()
        plan = self.adapter.plan_install(self.catalog)
        store = TransactionStore(self.home, self.paths, frozenset({self.path}))
        with self.assertRaises(SafetyError):
            store.execute(plan)
        self.assertFalse(self.paths.state.exists())

    def test_crlf_multiline_clone_keeps_line_endings_and_value(self):
        content = (b'[profiles]\r\n [[default]]\r\n  custom_command = """echo one\r\n'
                   b'[[not a section]]\r\necho two"""\r\n')
        original = self.fixture(content)
        self.install()
        raw = self.path.read_bytes()
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        document = TerminatorConfig(raw)
        for name in PROFILE_NAMES.values():
            self.assertEqual(document.profile(name)["custom_command"],
                             document.profile("default")["custom_command"])
        self.assertEqual(document.without_managed_profiles(), original)

    def test_excessive_config_nesting_is_refused_without_modifying_file(self):
        content = b"\n".join(("[" * depth + "synthetic" + "]" * depth).encode()
                             for depth in range(1, 66))
        self.fixture(content)
        before = self.tree()
        with self.assertRaises(SafetyError):
            self.adapter.plan_install(self.catalog)
        self.assertEqual(self.tree(), before)



    def test_forged_plan_cannot_drop_default_even_with_consistent_hashes(self):
        self.fixture()
        before = self.tree()
        plan = self.adapter.plan_install(self.catalog)
        item = plan.changes[0]
        document = TerminatorConfig(item.content)
        span = document.spans[("profiles", "default")]
        content = item.content[:span.start] + item.content[span.end:]
        record = replace(plan.manifest.resources[str(self.path)], sha256=digest(content))
        manifest = replace(plan.manifest, resources=MappingProxyType({str(self.path): record}))
        forged = replace(plan, changes=(replace(item, content=content),), manifest=manifest)
        with self.assertRaises(ConflictError):
            self.adapter.store.execute(forged)
        self.assertEqual(self.tree(), before)

    def test_empty_profiles_header_without_newline_is_handled_safely(self):
        self.fixture(b"[profiles]")
        self.install()
        document = TerminatorConfig(self.path.read_bytes())
        self.assertEqual(set(document.managed_sections()), set(PROFILE_NAMES.values()))
        self.assertNotIn("default", document.parsed["profiles"])



    def test_installed_cli_roundtrip_with_fake_executable(self):
        original = self.fixture()
        directory = self.home / "bin"
        directory.mkdir()
        executable = directory / "terminator"
        executable.write_text("#!/bin/sh\nexit 99\n")
        executable.chmod(0o700)
        env = dict(os.environ, PATH=str(directory) + os.pathsep + os.defpath)

        def cli(*args):
            result = subprocess.run([sys.executable, "-m", "aeronox", *args], env=env,
                                    cwd=self.home, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

        cli("install", "--components", "terminator", "--dry-run")
        self.assertFalse(self.paths.state.exists())
        cli("install", "--components", "terminator")
        installed = self.tree()
        cli("install", "--components", "terminator")
        self.assertEqual(self.tree(), installed)
        output = cli("open", "terminator", "--palette", "aviation-red", "--dry-run",
                     "--", "--working-directory", "/tmp/with spaces")
        self.assertEqual(json.loads(output)[0], str(executable))
        self.assertEqual(json.loads(output)[-2:], ["--working-directory", "/tmp/with spaces"])
        self.assertIn("committed", cli("backup", "list"))
        self.assertEqual(TerminatorConfig(self.path.read_bytes()).without_managed_profiles(),
                         original)


if __name__ == "__main__":
    unittest.main()
