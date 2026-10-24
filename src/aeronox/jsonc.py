"""Read-only JSONC decoder: comments and trailing commas, without editing settings."""

import json

from aeronox.storage import SafetyError


def parse_jsonc(content: bytes) -> object:
    try:
        text = content.decode("utf-8-sig")
        clean = list(text)
        index = 0
        quoted = False
        while index < len(text):
            char = text[index]
            if quoted:
                if char == "\\":
                    index += 2
                    continue
                if char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif text[index:index + 2] == "//":
                while index < len(text) and text[index] not in "\r\n":
                    clean[index] = " "
                    index += 1
                continue
            elif text[index:index + 2] == "/*":
                end = text.find("*/", index + 2)
                if end == -1:
                    raise ValueError("Unterminated comment")
                for position in range(index, end + 2):
                    if text[position] not in "\r\n":
                        clean[position] = " "
                index = end + 2
                continue
            index += 1
        text = "".join(clean)
        quoted = False
        index = 0
        previous = ""
        while index < len(text):
            char = text[index]
            if quoted:
                if char == "\\":
                    index += 2
                    continue
                if char == '"':
                    quoted = False
                    previous = '"'
            elif char == '"':
                quoted = True
            elif char == ",":
                following = index + 1
                while following < len(text) and text[following].isspace():
                    following += 1
                if (following < len(text) and text[following] in "]}"
                        and previous and previous not in "[{,:"):
                    clean[index] = " "
                previous = char
            elif not char.isspace():
                previous = char
            index += 1

        def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate key")
                result[key] = value
            return result

        def invalid_constant(value: str) -> None:
            raise ValueError("Non-finite constant")

        return json.loads("".join(clean), object_pairs_hook=unique, parse_constant=invalid_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise SafetyError("Invalid or unsupported JSONC (details redacted)") from exc
