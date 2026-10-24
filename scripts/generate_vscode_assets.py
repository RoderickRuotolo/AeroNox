"""Generate/check reference snippets using the installed AeroNox palette catalog."""

import argparse
from pathlib import Path

from aeronox.adapters.vscode_theme import snippet
from aeronox.catalog import PaletteCatalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check examples without writing")
    args = parser.parse_args()
    output_dir = Path(__file__).resolve().parents[1] / "assets/vscode"
    for palette in PaletteCatalog().list():
        path = output_dir / f"{palette.id}.settings.jsonc"
        content = snippet(palette)
        if args.check:
            if not path.is_file() or path.read_bytes() != content:
                parser.exit(1, "VS Code reference assets are missing or stale; regenerate them.\n")
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
