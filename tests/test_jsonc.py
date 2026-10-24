"""JSONC read-only parsing: never sanitize or rewrite a real settings file."""

import unittest

from aeronox.jsonc import parse_jsonc
from aeronox.storage import SafetyError


class JSONCTests(unittest.TestCase):
    def test_comments_trailing_commas_bom_and_crlf(self):
        source = (b'\xef\xbb\xbf{ // line comment\r\n "a": [1, 2, /* block */], '
                  b'"nested": {"ok": true,}, }')
        self.assertEqual(parse_jsonc(source), {"a": [1, 2], "nested": {"ok": True}})

    def test_comment_markers_and_commas_inside_strings_are_preserved(self):
        self.assertEqual(parse_jsonc(b'{"url":"https://example.test/a/*b*/", "x":"a,}",}'),
                         {"url": "https://example.test/a/*b*/", "x": "a,}"})
        self.assertEqual(parse_jsonc(br'{"x":"escaped \" // still string",}'),
                         {"x": 'escaped " // still string'})

    def test_invalid_or_ambiguous_input_is_refused_with_redacted_details(self):
        invalid = [b"", b"/* missing end", b'{"a":1,"a":2}', b"[,]", b"[1,,]",
                   b'{"a":,}', b'{"a":1,,}', b'{"x":NaN}', b'{"x":Infinity}',
                   b'{"x":-Infinity}', b'"SYNTHETIC_SECRET', b'\xff', b'{"a":\x00}']
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(SafetyError) as result:
                parse_jsonc(source)
            self.assertNotIn("SYNTHETIC_SECRET", str(result.exception))

    def test_nested_arrays_with_string_escapes(self):
        self.assertEqual(parse_jsonc(br'{"a":[{"b":"\\",},[false,null,],],}'),
                         {"a": [{"b": "\\"}, [False, None]]})


if __name__ == "__main__":
    unittest.main()
