"""ConfigObj validation plus a lossless index of original section byte ranges.

ConfigObj is the semantic parser. The source indexer only locates sections for
splicing; ambiguous syntax is refused instead of reformatting personal settings.
"""

import re
from copy import deepcopy
from dataclasses import dataclass

from configobj import ConfigObj, ConfigObjError, Section

from aeronox.models import Palette
from aeronox.storage import ConflictError, SafetyError

PROFILE_NAMES = {
    "aviation-red": "AeroNox Aviation Red",
    "nvis-green-a": "AeroNox NVIS Green A",
}
HEADER = re.compile(
    r'''^[ \t]*(\[+)[ \t]*("[^"]*"|'[^']*'|[^'"\[\]#\r\n]+?)[ \t]*(\]+)[ \t]*(?:\#.*)?$'''
)
ASSIGNMENT = re.compile(r'''^[ \t]*(?:"[^"]*"|'[^']*'|[^=]+?)[ \t]*=[ \t]*(.*)$''')


@dataclass
class Span:
    path: tuple[str, ...]
    start: int
    end: int


class TerminatorConfig:
    def __init__(self, content: bytes):
        self.content = content
        try:
            text = content.decode("utf-8-sig")
            if "\x00" in text or "\r" in text.replace("\r\n", ""):
                raise ValueError
            self.parsed = ConfigObj(text.splitlines(), encoding="utf-8", interpolation=False,
                                    raise_errors=True)
        except (ConfigObjError, UnicodeError, ValueError, RecursionError) as exc:
            # ConfigObj errors can include complete lines containing private commands.
            raise SafetyError("Invalid Terminator ConfigObj document (details redacted)") from exc
        self.newline = b"\r\n" if b"\r\n" in content else b"\n"
        self.spans = self._index(text)
        expected: set[tuple[str, ...]] = set()

        def walk(section: Section, prefix: tuple[str, ...] = ()) -> None:
            for name in section.sections:
                path = (*prefix, name)
                expected.add(path)
                walk(section[name], path)

        walk(self.parsed)
        if expected != set(self.spans):
            raise SafetyError("Unsupported ConfigObj section syntax; no changes made")
        profiles = self.parsed.get("profiles")
        if profiles is not None and not isinstance(profiles, Section):
            raise SafetyError("Terminator profiles must be a ConfigObj section")

    def _index(self, text: str) -> dict[tuple[str, ...], Span]:
        spans = {}
        stack: list[Span] = []
        offset = 3 if self.content.startswith(b"\xef\xbb\xbf") else 0
        multiline = None
        for raw in text.splitlines(keepends=True):
            line = raw.rstrip("\r\n")
            if multiline is not None:
                if multiline in line:
                    multiline = None
            elif not line.lstrip().startswith("#"):
                header = HEADER.fullmatch(line)
                if header is not None:
                    opening, name, closing = header.groups()
                    depth = len(opening)
                    if depth != len(closing) or depth > len(stack) + 1 or depth > 64:
                        raise SafetyError("Unsupported ConfigObj section nesting")
                    while len(stack) >= depth:
                        stack.pop().end = offset
                    name = name.strip()
                    if name.startswith(("'", '"')):
                        name = name[1:-1]
                    path = (*(span.path[-1] for span in stack), name)
                    span = Span(path, offset, len(self.content))
                    spans[path] = span
                    stack.append(span)
                elif line.lstrip().startswith("["):
                    raise SafetyError("Unsupported ConfigObj section header")
                else:
                    assignment = ASSIGNMENT.fullmatch(line)
                    if assignment is not None:
                        value = assignment.group(1).lstrip()
                        for delimiter in ('"""', "'''"):
                            if value.startswith(delimiter) and delimiter not in value[3:]:
                                multiline = delimiter
            offset += len(raw.encode("utf-8"))
        return spans

    def profile(self, name: str) -> dict[str, object]:
        profiles = self.parsed.get("profiles", {})
        if name not in profiles:
            if name == "default":
                return {}  # Terminator supplies its built-in default; do not create/modify it.
            raise SafetyError("Base profile does not exist; select an existing --base-profile")
        if not isinstance(profiles[name], Section):
            raise SafetyError("Selected profile is not a ConfigObj section")
        return profiles[name].dict()

    def managed_sections(self) -> dict[str, bytes]:
        return {name: self.content[span.start:span.end]
                for name in PROFILE_NAMES.values()
                if (span := self.spans.get(("profiles", name))) is not None}

    def with_profiles(self, blocks: dict[str, bytes]) -> bytes:
        existing = self.managed_sections()
        if existing:
            if set(existing) != set(blocks):
                raise ConflictError("A managed profile was removed or renamed")
            edits = [(self.spans[("profiles", name)].start,
                      self.spans[("profiles", name)].end, block)
                     for name, block in blocks.items()]
            return self._splice(edits)
        if any(name in self.parsed.get("profiles", {}) for name in blocks):
            raise SafetyError("A profile name is already used by a scalar setting")
        section = self.spans.get(("profiles",))
        combined = b"".join(blocks.values())
        if section is None:
            prefix = self.newline if self.content and not self.content.endswith(b"\n") else b""
            return self.content + prefix + b"[profiles]" + self.newline + combined
        children = [span.start for path, span in self.spans.items()
                    if len(path) == 2 and path[0] == "profiles"]
        offset = min(children) if children else section.end
        prefix = self.newline if offset and self.content[offset - 1:offset] != b"\n" else b""
        return self._splice([(offset, offset, prefix + combined)])

    def without_managed_profiles(self) -> bytes:
        return self._splice([(span.start, span.end, b"") for name in PROFILE_NAMES.values()
                             if (span := self.spans.get(("profiles", name))) is not None])

    def _splice(self, edits: list[tuple[int, int, bytes]]) -> bytes:
        result = self.content
        for start, end, replacement in sorted(edits, reverse=True):
            result = result[:start] + replacement + result[end:]
        return result


def read_managed_sections(content: bytes) -> dict[str, bytes]:
    return TerminatorConfig(content).managed_sections()


def validate_shared_edit(before: bytes, after: bytes) -> None:
    """Prove that a plan cannot rewrite default or any other personal bytes."""
    original = TerminatorConfig(before)
    proposed = TerminatorConfig(after)
    unowned = original.without_managed_profiles()
    remaining = proposed.without_managed_profiles()
    if remaining == unowned:
        return
    profiles = original.spans.get(("profiles",))
    if profiles is None:
        prefix = original.newline if before and not before.endswith(b"\n") else b""
        if remaining == before + prefix + b"[profiles]" + original.newline:
            return
    elif (not original.managed_sections() and profiles.end == len(before)
          and before and not before.endswith(b"\n")
          and not any(path[:1] == ("profiles",) and len(path) > 1 for path in original.spans)
          and remaining == before + original.newline):
        return
    raise ConflictError("Personal Terminator bytes differ from the proposed section-only edit")


def profile_block(base: dict[str, object], palette: Palette, newline: bytes) -> bytes:
    profile = deepcopy(base)
    profile.update({
        "use_theme_colors": "False", "background_type": "solid",
        "foreground_color": palette.colors["foreground"],
        "background_color": palette.colors["background"],
        "palette": ":".join(palette.ansi16),
    })
    # Cursor setting names vary across releases; only override names present in the base.
    supported = [key for key in ("cursor_color", "cursor_bg_color", "cursor_fg_color")
                 if key in base]
    for key in supported:
        profile[key] = (palette.colors["background"] if key == "cursor_fg_color"
                        else palette.colors["cursor"])
    if supported:
        profile["cursor_color_default"] = "False"
    config = ConfigObj({"profiles": {PROFILE_NAMES[palette.id]: profile}},
                       encoding="utf-8", interpolation=False)
    config.indent_type = "  "
    try:
        lines = config.write()
    except (ConfigObjError, ValueError) as exc:
        raise SafetyError("Cannot serialize the selected profile safely") from exc
    return b"\n".join(lines[1:]).replace(b"\n", newline) + newline
