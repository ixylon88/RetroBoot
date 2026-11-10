"""Checks for the independent VGA evidence reader."""

import unittest

from tools.test_menu import screen_rows


class ScreenEvidenceTests(unittest.TestCase):
    def test_vga_characters_are_decoded_separately_from_attributes(self):
        page = bytearray(b" \x17" * 2000)
        page[0:4] = bytes((0xDA, 0x70, 0xC4, 0x1F))
        page[-2:] = b"Z\x17"
        rows = screen_rows(page)
        self.assertEqual((len(rows), len(rows[0])), (25, 80))
        self.assertEqual(rows[0][:2], "\u250c\u2500")
        self.assertEqual(rows[-1][-1], "Z")

    def test_incomplete_or_oversized_capture_is_rejected(self):
        for length in (0, 3999, 4001):
            with self.subTest(length=length), self.assertRaises(ValueError):
                screen_rows(bytes(length))


if __name__ == "__main__":
    unittest.main()
