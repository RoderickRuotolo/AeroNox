import json
import subprocess
import sys

import pytest

from aeronox import __version__
from aeronox.cli import main


@pytest.mark.parametrize("args", [["--help"], ["palette", "--help"], ["--version"]])
def test_help_and_version(args, capsys):
    with pytest.raises(SystemExit) as result:
        main(args)
    assert result.value.code == 0
    output = capsys.readouterr().out
    assert __version__ in output if args == ["--version"] else "usage:" in output


def test_list_and_show(capsys):
    assert main(["palette", "list"]) == 0
    assert "nvis-green-a" in capsys.readouterr().out
    assert main(["palette", "show", "aviation-red"]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == "aviation-red"


def test_invalid_palette(capsys):
    with pytest.raises(SystemExit) as result:
        main(["palette", "show", "unknown"])
    assert result.value.code == 1
    assert "Unknown palette" in capsys.readouterr().err


@pytest.mark.parametrize("args", [[], ["apply", "aviation-red"]])
def test_unimplemented_commands_fail_honestly(args):
    with pytest.raises(SystemExit) as result:
        main(args)
    assert result.value.code == 2


def test_doctor_without_apps(monkeypatch, capsys, isolated_home):
    monkeypatch.setattr("aeronox.cli.shutil.which", lambda _: None)
    monkeypatch.setenv("COLORTERM", "truecolor")
    assert main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "terminator: not found" in output
    assert "advertised (not verified)" in output
    assert "assisted integration" in output
    assert str(isolated_home) not in output


def test_contrast_report(capsys):
    assert main(["palette", "contrast"]) == 0
    output = capsys.readouterr().out
    assert "aviation-red:" in output and "nvis-green-a:" in output
    assert "no NVIS certification" in output


def test_commands_do_not_write_or_launch_apps(isolated_home, monkeypatch):
    sentinel = isolated_home / ".vimrc"
    sentinel.write_bytes(b"personal config\n")
    before = {p.relative_to(isolated_home): p.read_bytes()
              for p in isolated_home.rglob("*") if p.is_file()}

    def forbidden(*args, **kwargs):
        pytest.fail("Read-only CLI launched a process")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    for args in (["doctor"], ["palette", "list"], ["palette", "show", "aviation-red"],
                 ["palette", "contrast"], ["install", "--dry-run"], ["backup", "list"]):
        assert main(args) == 0
    after = {p.relative_to(isolated_home): p.read_bytes()
             for p in isolated_home.rglob("*") if p.is_file()}
    assert before == after
    assert sorted(p.name for p in isolated_home.iterdir()) == [".vimrc"]


def test_module_entrypoint(tmp_path):
    result = subprocess.run([sys.executable, "-m", "aeronox", "palette", "list"],
                            cwd=tmp_path, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "aviation-red" in result.stdout


def test_missing_vscode_does_not_write(isolated_home, capsys, monkeypatch):
    monkeypatch.setattr("aeronox.adapters.vscode.shutil.which", lambda _: None)
    assert main(["install", "--components", "vscode"]) == 0
    assert "skipped" in capsys.readouterr().out
    assert list(isolated_home.iterdir()) == []


@pytest.mark.parametrize("components", ["", "unknown", "vim,vim", "vim, htop"])
def test_invalid_components(components):
    with pytest.raises(SystemExit) as result:
        main(["install", "--dry-run", "--components", components])
    assert result.value.code == 2
