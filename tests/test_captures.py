"""Validate committed native terminal recordings without launching GUI applications."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aeronox.catalog import PaletteCatalog

ROOT = Path(__file__).parent.parent / "docs/screenshots"


class NativeCaptureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aeronox capture checks ")
        self.addCleanup(temporary.cleanup)
        home = Path(temporary.name)
        environment = patch.dict(os.environ, {
            "HOME": str(home), "XDG_CONFIG_HOME": str(home / "config"),
            "XDG_STATE_HOME": str(home / "state"), "XDG_DATA_HOME": str(home / "data"),
        })
        environment.start()
        self.addCleanup(environment.stop)

    def test_recordings_are_valid_asciicast_with_palette_metadata(self):
        for palette in PaletteCatalog().list():
            for app in ("vim", "htop"):
                with self.subTest(app=app, palette=palette.id):
                    path = ROOT / f"{app}-{palette.id}.cast"
                    items = [json.loads(line) for line in path.read_text().splitlines()]
                    header, events = items[0], items[1:]
                    self.assertEqual(header["version"], 2)
                    self.assertEqual((header["width"], header["height"]), (100, 28))
                    self.assertEqual(header["theme"]["fg"], palette.colors["foreground"])
                    self.assertEqual(header["theme"]["bg"], palette.colors["background"])
                    self.assertEqual(header["theme"]["palette"].split(":"), list(palette.ansi16))
                    self.assertEqual(header["env"], {"TERM": "xterm-256color"})
                    self.assertGreater(len(events), 1)
                    self.assertEqual([item[0] for item in events],
                                     sorted(item[0] for item in events))
                    self.assertTrue(all(item[1] in {"o", "m"} for item in events))
                    self.assertGreaterEqual(header["duration"], events[-1][0])
                    output = "".join(item[2] for item in events if item[1] == "o")
                    self.assertIn("\x1b[", output)
                    self.assertNotIn(str(Path(__file__).parent.parent), output)
                    self.assertNotIn("SYNTHETIC_SECRET", output)
                    if app == "vim":
                        self.assertIn("theme_for_altitude", output)
                        rgb = ";".join(str(int(palette.colors["foreground"][i:i + 2], 16))
                                       for i in (1, 3, 5))
                        self.assertIn("38;2;" + rgb, output)
                    else:
                        for label in ("Help", "Setup", "Quit"):
                            self.assertIn(label, output)


if __name__ == "__main__":
    unittest.main()
