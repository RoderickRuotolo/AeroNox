"""Assisted VS Code setup uses synthetic profiles in temporary HOME/XDG only."""

import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

from aeronox.adapters.vscode import VSCodeAdapter, guide, installations
from aeronox.adapters.vscode_theme import (
    ANSI_NAMES,
    PROFILE_NAMES,
    contains_settings,
    snippet,
    theme_settings,
)
from aeronox.catalog import PaletteCatalog
from aeronox.cli import main
from aeronox.jsonc import parse_jsonc
from aeronox.storage import ConflictError, SafetyError
from aeronox.transactions import TransactionError


class VSCodeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aeronox vscode ")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / "home with spaces"
        self.home.mkdir(mode=0o700)
        environment = patch.dict(os.environ, {
            "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "config"),
            "XDG_STATE_HOME": str(self.home / "state"), "XDG_DATA_HOME": str(self.home / "data"),
            "HTOPRC": "", "VSCODE_PORTABLE": "",
        })
        environment.start()
        self.addCleanup(environment.stop)
        detection = patch("aeronox.adapters.vscode.shutil.which",
                          side_effect=lambda name: "/synthetic/code" if name == "code" else None)
        detection.start()
        self.addCleanup(detection.stop)
        self.adapter = VSCodeAdapter()
        self.catalog = PaletteCatalog()

    def tree(self):
        return {str(p.relative_to(self.home)): p.read_bytes() if p.is_file() else None
                for p in self.home.rglob("*")}

    def install(self):
        return self.adapter.install(self.adapter.plan_install(self.catalog))

    def profile(self, palette="aviation-red", *, adapter=None, flags=None):
        adapter = adapter or self.adapter
        root = adapter.selected().data_root
        registry = root / "User/globalStorage/storage.json"
        entries = (json.loads(registry.read_bytes()).get("userDataProfiles", [])
                   if registry.exists() else [])
        location = "synthetic-red" if palette == "aviation-red" else "synthetic-green"
        entry = {"name": PROFILE_NAMES[palette], "location": location}
        if flags is not None:
            entry["useDefaultFlags"] = flags
        entries.append(entry)
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({"userDataProfiles": entries,
                                        "privateUnrelatedField": "SYNTHETIC_SECRET"}))
        settings = root / "User/profiles" / location / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_bytes(snippet(self.catalog.get(palette)))
        default = root / "User/settings.json"
        default.write_bytes(b'{"personalDefault":"SYNTHETIC_DEFAULT_SECRET"}')
        return registry, settings, default

    def capture(self, args):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(args), 0)
        return output.getvalue()

    def test_snippets_cover_workbench_textmate_semantic_and_16_ansi(self):
        for palette in self.catalog.list():
            data = parse_jsonc(snippet(palette))
            self.assertEqual(set(data), {"workbench.colorCustomizations",
                                        "editor.tokenColorCustomizations",
                                        "editor.semanticTokenColorCustomizations"})
            colors = data["workbench.colorCustomizations"]
            self.assertEqual(colors["editor.background"], palette.colors["background"])
            self.assertEqual(colors["editor.foreground"], palette.colors["foreground"])
            self.assertEqual([colors[f"terminal.ansi{name}"] for name in ANSI_NAMES],
                             list(palette.ansi16))
            self.assertEqual(sum(key.startswith("terminal.ansi") for key in colors), 16)
            self.assertTrue(data["editor.semanticTokenColorCustomizations"]["enabled"])
            invalid = data["editor.tokenColorCustomizations"]["textMateRules"][-1]
            self.assertIn("underline", invalid["settings"]["fontStyle"])
            allowed_colors = set(palette.colors.values()) | set(palette.ansi16)
            self.assertTrue(set(colors.values()) <= allowed_colors)

    def test_packaged_assets_match_single_source_generator_and_guide(self):
        for palette in self.catalog.list():
            resource = files("aeronox.vscode_assets").joinpath(f"{palette.id}.settings.jsonc")
            self.assertEqual(resource.read_bytes(), snippet(palette))
        self.assertIn("Never", guide().replace("never", "Never"))
        self.assertIn("Default", guide())

    def test_install_generates_owned_snippets_without_configuring_profiles(self):
        registry, settings, default = self.profile()
        before = {path: path.read_bytes() for path in (registry, settings, default)}
        result = self.install()
        self.assertTrue(result.changed)
        self.assertIn("manual profile setup required", result.message)
        self.assertTrue(self.adapter.verify().ok)
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)
        resources = self.adapter.store.planner().manifest.resources
        self.assertEqual(set(resources), {str(path) for path in self.adapter.targets.values()})
        for target in self.adapter.targets.values():
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_snippet_install_does_not_imply_profile_readiness(self):
        self.install()
        self.assertTrue(self.adapter.verify().ok)
        with self.assertRaises(SafetyError):
            self.adapter.open_command("aviation-red", [])
        self.assertFalse((self.adapter.selected().data_root / "User").exists())

    def test_dry_run_has_no_writes_or_processes(self):
        before = self.tree()
        with patch("aeronox.commands.subprocess.run", side_effect=AssertionError("spawned")):
            output = self.capture(["install", "--components", "vscode", "--dry-run"])
        self.assertIn("reference snippets", output)
        self.assertIn("no profiles were configured", output)
        self.assertEqual(self.tree(), before)

    def test_reinstall_is_idempotent(self):
        self.install()
        before = self.tree()
        self.assertFalse(self.install().changed)
        self.assertEqual(self.tree(), before)

    def test_modified_or_unmanaged_assets_are_never_overwritten(self):
        target = self.adapter.targets["aviation-red"]
        target.parent.mkdir(parents=True)
        target.write_bytes(b"// personal artifact")
        with self.assertRaises(ConflictError):
            self.adapter.plan_install(self.catalog)
        self.assertEqual(target.read_bytes(), b"// personal artifact")
        target.unlink()
        self.install()
        target.write_bytes(target.read_bytes() + b"// personal changes\n")
        with self.assertRaises(ConflictError):
            self.adapter.plan_install(self.catalog)
        with self.assertRaises(ConflictError):
            self.adapter.plan_uninstall()

    def test_failure_rolls_back_snippets_without_touching_default(self):
        _, _, default = self.profile()
        original = default.read_bytes()
        plan = self.adapter.plan_install(self.catalog)
        replace_file = self.adapter.store.files.replace

        def fail(path, *args, **kwargs):
            if path == self.adapter.store.state:
                raise OSError("Injected failure")
            return replace_file(path, *args, **kwargs)

        with patch.object(self.adapter.store.files, "replace", side_effect=fail):
            with self.assertRaises(TransactionError):
                self.adapter.install(plan)
        self.assertTrue(all(not path.exists() for path in self.adapter.targets.values()))
        self.assertEqual(default.read_bytes(), original)

    def test_uninstall_removes_only_snippets_and_preserves_manual_profiles(self):
        self.profile()
        profile_root = self.adapter.selected().data_root
        before = {p: p.read_bytes() for p in profile_root.rglob("*") if p.is_file()}
        self.install()
        self.adapter.store.execute(self.adapter.plan_uninstall())
        self.assertTrue(all(not p.exists() for p in self.adapter.targets.values()))
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)

    def test_prepared_profile_is_checked_read_only_without_default_reads(self):
        registry, settings, default = self.profile()
        original_read = self.adapter.store.files.read

        def read(path):
            if path == default:
                self.fail("Default settings must never be inspected")
            return original_read(path)

        before = self.tree()
        with patch.object(self.adapter.store.files, "read", side_effect=read):
            self.assertEqual(self.adapter.prepared_profile("aviation-red"),
                             PROFILE_NAMES["aviation-red"])
        self.assertEqual(self.tree(), before)

    def test_missing_or_empty_profile_never_launches_or_creates_one(self):
        for args in (["open", "code"], ["open", "code", "--palette", "aviation-red"]):
            before = self.tree()
            with patch("aeronox.commands.subprocess.run", side_effect=AssertionError("spawned")):
                with redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as result:
                        main(args)
            self.assertEqual(result.exception.code, 1)
            self.assertEqual(self.tree(), before)
        _, settings, _ = self.profile()
        settings.write_text("{}")
        with self.assertRaisesRegex(SafetyError, "not prepared"):
            self.adapter.open_command("aviation-red", [])

    def test_prepared_argv_pins_edition_data_root_and_new_window(self):
        self.profile()
        args = ["/tmp/project with spaces", "literal ; $(data)"]
        self.assertEqual(self.adapter.open_command("aviation-red", args), [
            "/synthetic/code", "--user-data-dir", str(self.adapter.selected().data_root),
            "--new-window", "--profile", PROFILE_NAMES["aviation-red"], *args,
        ])

    def test_cli_launch_is_shell_free_and_propagates_exit_code(self):
        self.profile()
        before = self.tree()
        with patch("aeronox.commands.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 5)) as run:
            self.assertEqual(main(["open", "code", "--palette", "aviation-red", "--",
                                   "/tmp/project with spaces"]), 5)
        self.assertIn(PROFILE_NAMES["aviation-red"], run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs, {"check": False})
        self.assertEqual(self.tree(), before)

    def test_cli_preview_and_status_hide_private_metadata(self):
        self.profile()
        before = self.tree()
        output = self.capture(["open", "code", "--palette", "aviation-red", "--dry-run"])
        self.assertIn(PROFILE_NAMES["aviation-red"], json.loads(output))
        output = self.capture(["vscode", "status"])
        self.assertIn("aviation-red: ready", output)
        self.assertIn("nvis-green-a: manual setup pending", output)
        self.assertNotIn("SYNTHETIC_SECRET", output)
        self.assertNotIn(str(self.home), output)
        self.assertNotIn("synthetic-red", output)
        paths = self.capture(["vscode", "status", "--paths"])
        self.assertIn(str(self.home), paths)
        self.assertEqual(self.tree(), before)

    def test_jsonc_settings_preserve_comments_fonts_and_existing_token_rules(self):
        _, settings, _ = self.profile()
        data = theme_settings(self.catalog.get("aviation-red"))
        data["editor.fontSize"] = 17
        data["private.setting"] = "https://example.test/secret/*literal*/"
        rules = data["editor.tokenColorCustomizations"]["textMateRules"]
        data["editor.tokenColorCustomizations"]["textMateRules"] = [{"scope": ["custom"]}, *rules]
        source = "// SYNTHETIC_PRIVATE_COMMENT\n" + json.dumps(data)
        source = source[:-1] + ",\n}"
        settings.write_text(source)
        self.adapter.prepared_profile("aviation-red")
        self.assertEqual(settings.read_text(), source)

    def test_wrong_palette_or_missing_ansi_fails_preparation(self):
        _, settings, _ = self.profile()
        data = theme_settings(self.catalog.get("nvis-green-a"))
        settings.write_text(json.dumps(data))
        with self.assertRaises(SafetyError):
            self.adapter.prepared_profile("aviation-red")
        data = theme_settings(self.catalog.get("aviation-red"))
        del data["workbench.colorCustomizations"]["terminal.ansiBrightWhite"]
        settings.write_text(json.dumps(data))
        with self.assertRaises(SafetyError):
            self.adapter.prepared_profile("aviation-red")

    def test_default_inheritance_is_refused(self):
        self.profile(flags={"settings": True})
        with self.assertRaisesRegex(SafetyError, "independent"):
            self.adapter.prepared_profile("aviation-red")

    def test_duplicate_names_or_locations_are_refused(self):
        registry, _, _ = self.profile()
        original = json.loads(registry.read_bytes())
        for duplicate in (copy.deepcopy(original["userDataProfiles"][0]),
                          {"name": "Other personal", "location": "synthetic-red"}):
            data = copy.deepcopy(original)
            data["userDataProfiles"].append(duplicate)
            registry.write_text(json.dumps(data))
            with self.subTest(duplicate=duplicate), self.assertRaises(SafetyError):
                self.adapter.prepared_profile("aviation-red")

    def test_malicious_or_legacy_profile_locations_are_refused(self):
        registry, _, default = self.profile()
        for location in ("../..", "default", "Default", "builtin", "/tmp/escape", "a/b",
                         "file:///tmp/escape", {"scheme": "file", "path": str(default)}):
            registry.write_text(json.dumps({"userDataProfiles": [
                {"name": PROFILE_NAMES["aviation-red"], "location": location}
            ]}))
            with self.subTest(location=location), self.assertRaises(SafetyError):
                self.adapter.prepared_profile("aviation-red")

    def test_symlink_settings_and_registry_are_not_followed(self):
        registry, settings, default = self.profile()
        settings.unlink()
        settings.symlink_to(default)
        with self.assertRaises(SafetyError):
            self.adapter.prepared_profile("aviation-red")
        settings.unlink()
        settings.write_bytes(snippet(self.catalog.get("aviation-red")))
        registry.unlink()
        registry.symlink_to(default)
        with self.assertRaises(SafetyError):
            self.adapter.prepared_profile("aviation-red")
        self.assertIn(b"SYNTHETIC_DEFAULT_SECRET", default.read_bytes())

    def test_corrupt_jsonc_details_never_leak_in_diagnostics(self):
        _, settings, _ = self.profile()
        settings.write_bytes(b'{"PRIVATE_SYNTHETIC_BROKEN_SECRET"')
        output = self.capture(["vscode", "status"])
        self.assertIn("details redacted", output)
        self.assertNotIn("PRIVATE_SYNTHETIC_BROKEN_SECRET", output)

    def test_concurrent_profile_change_aborts_before_launch(self):
        _, settings, _ = self.profile()
        original_read = self.adapter.store.files.read
        seen = []

        def read(path):
            if path == settings:
                seen.append(path)
                if len(seen) == 2:
                    settings.write_bytes(settings.read_bytes() + b"\n")
            return original_read(path)

        with patch.object(self.adapter.store.files, "read", side_effect=read):
            with self.assertRaises(ConflictError):
                self.adapter.open_command("aviation-red", [])

    def test_profile_selector_overrides_cannot_bypass_checks(self):
        for args in (["--profile", "New empty"], ["--profile=Default"], ["--user-data-dir=/tmp"],
                     ["--profile-temp"], ["--reuse-window"], ["-r"]):
            with self.subTest(args=args), self.assertRaises(SafetyError):
                self.adapter.open_command("aviation-red", args)

    def test_explicit_original_mode_does_not_append_profile(self):
        self.assertEqual(self.adapter.open_command("original", ["/tmp/project"]),
                         ["/synthetic/code", "/tmp/project"])
        output = self.capture(["open", "code", "--palette", "original", "--dry-run"])
        self.assertEqual(json.loads(output), ["/synthetic/code"])
        self.assertEqual(self.tree(), {})

    def test_stable_insiders_and_codium_have_separate_roots(self):
        with patch("aeronox.adapters.vscode.shutil.which", side_effect=lambda name: f"/bin/{name}"):
            detected = {item.edition: item for item in installations(self.home, self.adapter.paths)}
        root = self.adapter.paths.config.parent
        self.assertEqual(detected["stable"].data_root, root / "Code")
        self.assertEqual(detected["insiders"].data_root, root / "Code - Insiders")
        self.assertEqual(detected["codium"].data_root, root / "VSCodium")
        self.assertEqual(detected["flatpak"].kind, "flatpak")

    def test_auto_prefers_native_edition_over_snap(self):
        mapping = {"code": "/snap/bin/code", "code-insiders": "/synthetic/code-insiders"}
        with patch("aeronox.adapters.vscode.shutil.which", side_effect=mapping.get):
            self.assertEqual(self.adapter.selected().edition, "insiders")

    def test_packaged_and_portable_detection_allows_snippets_but_not_themed_launch(self):
        for edition, executable in (("stable", "/snap/bin/code"),
                                    ("flatpak",
                                     "/var/lib/flatpak/exports/bin/com.visualstudio.code")):
            with self.subTest(edition=edition):
                command = "code" if edition == "stable" else "com.visualstudio.code"
                with patch("aeronox.adapters.vscode.shutil.which",
                           side_effect=lambda name: executable if name == command else None):
                    adapter = VSCodeAdapter(edition=edition)
                    self.assertTrue(adapter.detect().available)
                    self.assertNotEqual(adapter.selected().kind, "native")
                    self.assertEqual(len(adapter.plan_install(self.catalog).changes), 2)
                    with self.assertRaisesRegex(SafetyError, "manual launch"):
                        adapter.open_command("aviation-red", [])
        with patch.dict(os.environ, VSCODE_PORTABLE=str(self.home / "portable")):
            self.assertEqual(self.adapter.selected().kind, "portable")
            with self.assertRaises(SafetyError):
                self.adapter.open_command("aviation-red", [])

    def test_custom_native_data_root_is_verified_and_pinned(self):
        root = self.home / "custom code data"
        adapter = VSCodeAdapter(user_data_dir=root)
        self.profile(adapter=adapter)
        self.assertEqual(adapter.open_command("aviation-red", [])[2], str(root))
        output = self.capture(["open", "code", "--user-data-dir", str(root),
                               "--palette", "aviation-red", "--dry-run"])
        self.assertEqual(json.loads(output)[2], str(root))
        for invalid in (Path("relative"), self.home.parent / "outside"):
            with self.assertRaises(SafetyError):
                VSCodeAdapter(user_data_dir=invalid)

    def test_snippets_and_guide_are_available_without_any_editor(self):
        with patch("aeronox.adapters.vscode.shutil.which", return_value=None):
            output = self.capture(["vscode", "snippet", "aviation-red"])
            self.assertEqual(parse_jsonc(output.encode()),
                             theme_settings(self.catalog.get("aviation-red")))
            self.assertIn("independent", self.capture(["vscode", "guide"]))
            output = self.capture(["install", "--components", "vscode"])
            self.assertIn("skipped", output)
        self.assertEqual(self.tree(), {})

    def test_settings_match_is_conservative_about_arrays_and_boolean_types(self):
        self.assertFalse(contains_settings({"x": 1}, {"x": True}))
        self.assertTrue(contains_settings({"x": [0, 1, 2]}, {"x": [1, 2]}))
        self.assertFalse(contains_settings({"x": [1, 2, 0]}, {"x": [1, 2]}))

    def test_installed_cli_exports_snippets_without_launching_fake_editor(self):
        directory = self.home / "bin"
        directory.mkdir()
        executable = directory / "code"
        executable.write_text("#!/bin/sh\nexit 99\n")
        executable.chmod(0o700)
        env = {**os.environ, "PATH": str(directory) + os.pathsep + os.defpath}

        def cli(*args, expected=0):
            result = subprocess.run([sys.executable, "-m", "aeronox", *args], cwd=self.home,
                                    env=env, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, expected, result.stderr)
            return result

        cli("install", "--components", "vscode", "--dry-run")
        self.assertFalse(self.adapter.paths.state.exists())
        cli("install", "--components", "vscode")
        cli("open", "code", expected=1)
        self.profile()
        result = cli("open", "code", "--palette", "aviation-red", "--dry-run")
        self.assertIn(PROFILE_NAMES["aviation-red"], json.loads(result.stdout))
        result = cli("vscode", "snippet", "aviation-red")
        self.assertEqual(parse_jsonc(result.stdout.encode()),
                         theme_settings(self.catalog.get("aviation-red")))



    def test_insiders_and_codium_profiles_are_verified_in_their_own_roots(self):
        for edition, command in (("insiders", "code-insiders"), ("codium", "codium")):
            with self.subTest(edition=edition):
                with patch("aeronox.adapters.vscode.shutil.which",
                           side_effect=lambda name: f"/synthetic/{command}" if name == command
                           else None):
                    adapter = VSCodeAdapter(edition=edition)
                    self.profile("nvis-green-a", adapter=adapter)
                    argv = adapter.open_command("nvis-green-a", ["project with spaces"])
                    self.assertEqual(argv[0], f"/synthetic/{command}")
                    self.assertEqual(argv[2], str(adapter.selected().data_root))
                    self.assertIn(PROFILE_NAMES["nvis-green-a"], argv)

    def test_profile_in_wrong_edition_is_not_used(self):
        self.profile()
        with patch("aeronox.adapters.vscode.shutil.which",
                   side_effect=lambda name: "/synthetic/code-insiders"
                   if name == "code-insiders" else None):
            adapter = VSCodeAdapter(edition="insiders")
            with self.assertRaises(SafetyError):
                adapter.open_command("aviation-red", [])
        self.assertFalse((self.adapter.paths.config.parent / "Code - Insiders").exists())


if __name__ == "__main__":
    unittest.main()
