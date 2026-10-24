"""Every test runs against an isolated HOME and XDG tree."""

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home with spaces"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for key, directory in (
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_STATE_HOME", "state"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"),
    ):
        monkeypatch.setenv(key, str(home / directory))
    return home
