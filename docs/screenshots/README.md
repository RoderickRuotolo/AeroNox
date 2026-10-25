# Native terminal recordings

These asciicast v2 files contain real output from native applications in isolated
100x28 pseudoterminals, using temporary HOME/XDG directories and synthetic data:

| Recording | Content |
| --- | --- |
| [Vim Aviation Red](vim-aviation-red.cast) | Synthetic Python buffer, native True Color output |
| [Vim NVIS Green A inspired](vim-nvis-green-a.cast) | Same synthetic buffer, native True Color output |
| [htop Aviation Red](htop-aviation-red.cast) | Native monochrome controls and an isolated sleep process |
| [htop NVIS Green A inspired](htop-nvis-green-a.cast) | Same setup, separate managed htoprc |

The recording header declares the AeroNox terminal foreground/background/ANSI
palette for playback. htop uses the terminal's default colors in monochrome;
its output is not an element-by-element RGB implementation. Vim emits actual
True Color sequences, checked against the palette. Native process statistics vary
by machine. Usernames, hostnames, personal buffers/settings and project paths are
excluded from these demo outputs. Keyboard input and the environment beyond TERM
are not recorded. The sample process belongs to the capture script.

Play locally with an asciicast-compatible player, for example:

```bash
asciinema play docs/screenshots/vim-aviation-red.cast
asciinema play docs/screenshots/htop-nvis-green-a.cast
```

AeroNox does not install a player or upload recordings. The optional player has its
own installation requirements; the [format reference](https://docs.asciinema.org/manual/asciicast/v2/)
explains the local JSON event stream. Regenerate recordings with the installed
checkout and native Vim/htop available:

```bash
python scripts/capture_native.py
```

Existing recordings must first be reviewed/renamed manually; the script refuses
to overwrite them. It creates temporary configs, installs only into those roots,
applies each palette and captures actual `aeronox open` launches. No real dotfiles,
VS Code windows or Terminator sessions are used. The committed recordings are
validated by tests without launching a GUI.

Desktop screenshots of Terminator and VS Code, final legibility in real terminal
fonts/displays and interaction with already-open applications remain manual
validation items. The recorded terminal themes are inspired lighting palettes,
without NVIS certification or medical claims.
