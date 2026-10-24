from aeronox.paths import XDGPaths


def test_defaults(isolated_home):
    paths = XDGPaths.resolve({"HOME": str(isolated_home)})
    assert paths.config == isolated_home / ".config/aeronox"
    assert paths.state == isolated_home / ".local/state/aeronox"
    assert paths.data == isolated_home / ".local/share/aeronox"
    assert not paths.config.exists()


def test_custom_paths(isolated_home):
    paths = XDGPaths.resolve()
    assert paths.config == isolated_home / "config/aeronox"
    assert paths.state == isolated_home / "state/aeronox"
    assert paths.data == isolated_home / "data/aeronox"


def test_empty_and_relative_values(isolated_home):
    paths = XDGPaths.resolve({"HOME": str(isolated_home), "XDG_CONFIG_HOME": "relative",
                              "XDG_STATE_HOME": "", "XDG_DATA_HOME": "../relative"})
    assert paths == XDGPaths.resolve({"HOME": str(isolated_home)})
