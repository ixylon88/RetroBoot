"""Check encoding, field bounds and language isolation before native builds."""

import json
import re
import unittest

from tools.ui_text import (LANGUAGES, c_literal, catalog_metadata, checked_catalog,
                           load_catalog, output_name, render_header, unique_keys,
                           validate_catalog)


class MenuCatalogTests(unittest.TestCase):
    def test_both_catalogs_generate_ascii_source_with_distinct_translations(self):
        catalogs = [load_catalog(language) for language in LANGUAGES]
        self.assertEqual(set(catalogs[0]), set(catalogs[1]))
        self.assertNotEqual(catalogs[0]["SYSTEM_INFO"], catalogs[1]["SYSTEM_INFO"])
        for language, strings in zip(LANGUAGES, catalogs):
            header = render_header(strings, language)
            self.assertTrue(header.isascii())
            self.assertIn('#define RB_UI_LANGUAGE "' + language + '"', header)

    def test_cp437_umlauts_and_adjacent_characters_survive_c_escaping(self):
        literal = c_literal('ÄÖÜäöüßABC"\\')
        decoded = bytes(int(octal, 8) for octal in re.findall(r"\\([0-7]{3})", literal))
        self.assertEqual(decoded, bytes.fromhex("8e 99 9a 84 94 81 e1 41 42 43 22 5c"))
        self.assertEqual(len(literal), 2 + 4 * len(decoded))

    def test_unrepresentable_control_and_empty_strings_are_rejected(self):
        for value in ("", "a\0b", "a\nb", "a\tb", "a\x7fb", "Euro €"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_catalog(dict(load_catalog("en"), READ_ONLY=value))

    def test_translation_cannot_overwrite_adjacent_screen_field(self):
        with self.assertRaises(ValueError):
            validate_catalog(dict(load_catalog("en"), CHS_HEADS="x" * 14))
        validate_catalog(dict(load_catalog("en"), CHS_HEADS="ö" * 13))

    def test_missing_unknown_and_duplicate_keys_are_rejected(self):
        strings = load_catalog("en")
        del strings["PAGE"]
        with self.assertRaises(ValueError):
            validate_catalog(strings)
        with self.assertRaises(ValueError):
            validate_catalog(dict(load_catalog("en"), UNKNOWN="unknown"))
        with self.assertRaises(ValueError):
            json.loads('{"PAGE":"one","PAGE":"two"}', object_pairs_hook=unique_keys)

    def test_test_oracle_rejects_other_language_or_changed_catalog(self):
        manifest = {"ui": catalog_metadata("en")}
        self.assertEqual(checked_catalog(manifest, "en"), load_catalog("en"))
        with self.assertRaises(ValueError):
            checked_catalog(manifest, "de")
        manifest["ui"]["catalog_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            checked_catalog(manifest, "en")

    def test_output_directories_are_separate_and_cannot_escape_build(self):
        names = {output_name(kind, language) for kind in ("hdd", "hdd-repeat", "menu", "scan", "volume", "handoff", "config", "state", "visibility", "profile")
                 for language in LANGUAGES}
        self.assertEqual(len(names), 20)
        self.assertEqual(output_name("hdd", "en"), "hdd")
        self.assertEqual(output_name("hdd", "de"), "hdd-de")
        for language in ("fr", "../de", "", "EN"):
            with self.subTest(language=language), self.assertRaises(ValueError):
                output_name("hdd", language)
        with self.assertRaises(ValueError):
            output_name("../hdd", "en")


if __name__ == "__main__":
    unittest.main()
