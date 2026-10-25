"""Record native Vim/htop demos in temporary HOME/XDG; write new asciicast v2 files."""

import argparse
import codecs
import fcntl
import json
import os
import pty
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time
from pathlib import Path
from unittest.mock import patch

from aeronox.catalog import PaletteCatalog
from aeronox.commands import install_components
from aeronox.lifecycle import change_mode

SAMPLE = '''# Synthetic demo buffer; no personal files or configuration.
def theme_for_altitude(altitude):
    """Example only: choose a label for this demo."""
    if altitude > 1000:
        return "aviation-red"
    return "nvis-green-a"

print(theme_for_altitude(1500))
'''


def record(command: list[str], quit_keys: bytes, env: dict[str, str], home: Path) -> list[list]:
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 28, 100, 0, 0))
    process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave,
                               cwd=home, env=env, start_new_session=True)
    os.close(slave)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    events = []
    started = time.monotonic()
    try:
        while time.monotonic() - started < 1.5:
            readable, _, _ = select.select([master], [], [], 0.05)
            if readable:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    break
                if not data:
                    break
                text = decoder.decode(data)
                if text:
                    events.append([round(time.monotonic() - started, 6), "o", text])
        final = decoder.decode(b"", final=True)
        if final:
            events.append([round(time.monotonic() - started, 6), "o", final])
        if process.poll() is None:
            os.write(master, quit_keys)
        process.wait(timeout=5)
        if process.returncode != 0 or not events:
            raise RuntimeError("Native capture failed; no recording published")
        events.append([round(time.monotonic() - started, 6), "m", "End of isolated capture"])
        return events
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        os.close(master)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).resolve().parents[1] / "docs/screenshots")
    args = parser.parse_args()
    if not shutil.which("vim") or not shutil.which("htop"):
        parser.exit(1, "Native Vim and htop are required; install test applications separately.\n")
    names = [f"{app}-{palette.id}.cast" for palette in PaletteCatalog().list()
             for app in ("vim", "htop")]
    if any((args.output_dir / name).exists() for name in names):
        parser.exit(1, "Capture files already exist; review/rename them before recording again.\n")
    with tempfile.TemporaryDirectory(prefix="aeronox-capture-") as directory:
        home = Path(directory)
        env = {**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / "config"),
               "XDG_STATE_HOME": str(home / "state"), "XDG_DATA_HOME": str(home / "data"),
               "HTOPRC": "", "VIMINIT": "", "EXINIT": "", "GVIMINIT": "",
               "TERM": "xterm-256color", "LC_ALL": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
        source = home / "config/htop/htoprc"
        source.parent.mkdir(parents=True)
        source.write_text("fields=0 46 47 1\nleft_meters=CPU Memory\n"
                          "left_meter_modes=1 1\nright_meters=Tasks\nright_meter_modes=2\n"
                          "color_scheme=0\n")
        (home / "sample.py").write_text(SAMPLE)
        with patch.dict(os.environ, env):
            install_components(("htop", "vim"), dry_run=False)
            sleeper = subprocess.Popen(["/bin/sleep", "30"], cwd=home, env=env)
            try:
                for palette in PaletteCatalog().list():
                    change_mode(palette.id, dry_run=False)
                    for app in ("vim", "htop"):
                        app_args = (["-Nu", "NONE", "-i", "NONE", "-n", "--cmd",
                                     "syntax on", "--cmd", "set termguicolors", "-c",
                                     "set number laststatus=2 statusline=AeroNox_" + palette.id,
                                     "sample.py"] if app == "vim" else
                                    ["-U", "-p", str(sleeper.pid)])
                        command = [sys.executable, "-m", "aeronox", "open", app, "--", *app_args]
                        events = record(command, b"\x1b:qa!\r" if app == "vim" else b"q", env, home)
                        native_output = "".join(event[2] for event in events if event[1] == "o")
                        expected = "theme_for_altitude" if app == "vim" else "Quit"
                        private = (os.environ.get("USER", ""), os.uname().nodename)
                        if expected not in native_output or any(
                            value and value in native_output for value in private
                        ):
                            raise RuntimeError(
                                "Capture quality/privacy check failed; not published"
                            )
                        header = {"version": 2, "width": 100, "height": 28,
                                  "title": f"Native {app}: {palette.name} (isolated PTY)",
                                  "env": {"TERM": "xterm-256color"},
                                  "duration": events[-1][0], "theme": {
                                      "fg": palette.colors["foreground"],
                                      "bg": palette.colors["background"],
                                      "palette": ":".join(palette.ansi16)}}
                        args.output_dir.mkdir(parents=True, exist_ok=True)
                        destination = args.output_dir / f"{app}-{palette.id}.cast"
                        with destination.open("x", encoding="utf-8") as output:
                            for item in (header, *events):
                                output.write(json.dumps(item) + "\n")
                        print(destination.name)
            finally:
                if sleeper.poll() is None:
                    sleeper.terminate()
                sleeper.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
