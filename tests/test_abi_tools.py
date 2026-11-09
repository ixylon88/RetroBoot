"""Validate image boundaries and test-result interpretation without native tools."""

import struct
import tempfile
import unittest
from pathlib import Path

from tools.build_abi_probe import MAX_PAYLOAD, inspect_map, inspect_payload, make_image, prepare_output
from tools.setup_toolchain import sha256, verify
from tools.test_abi_probe import check_result


def sample_payload():
    data = bytearray(256)
    data[:10] = b"\xeb\x1eRBABI01\0"
    struct.pack_into("<11H", data, 10, 32, 32, 256, 280, 0x1000,
                     0xE000, 0xFFFE, 256, 1, 254, 256)
    return data


class ImageTests(unittest.TestCase):
    def test_header_and_memory_contract(self):
        h = inspect_payload(sample_payload())
        self.assertEqual((h["bss_begin"], h["bss_end"]), (256, 280))
        self.assertEqual(h["load_segment"] * 16 + h["stack_low"], 0x1E000)

    def test_wrong_header_or_jump(self):
        for offset in (0, 1, 2, 9):
            data = sample_payload()
            data[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                inspect_payload(data)

    def test_bad_format_fields(self):
        for index, value in ((0, 30), (1, 33), (8, 2)):
            data = sample_payload()
            struct.pack_into("<H", data, 10 + 2 * index, value)
            with self.subTest(index=index), self.assertRaises(ValueError):
                inspect_payload(data)

    def test_memory_contract_changes_need_explicit_support(self):
        for index, value in ((4, 0x2000), (5, 0xD000), (6, 0xFFFF)):
            data = sample_payload()
            struct.pack_into("<H", data, 10 + 2 * index, value)
            with self.subTest(index=index), self.assertRaises(ValueError):
                inspect_payload(data)

    def test_bss_cannot_overlap_file_or_stack(self):
        for index, value in ((2, 255), (3, 256), (3, 0xE001)):
            data = sample_payload()
            struct.pack_into("<H", data, 10 + 2 * index, value)
            with self.subTest(index=index), self.assertRaises(ValueError):
                inspect_payload(data)

    def test_wrong_declared_file_length(self):
        data = sample_payload()
        struct.pack_into("<H", data, 24, len(data) + 1)
        with self.assertRaises(ValueError):
            inspect_payload(data)

    def test_payload_must_fit_first_floppy_track(self):
        data = sample_payload() + bytes(MAX_PAYLOAD + 1 - 256)
        struct.pack_into("<H", data, 24, len(data))
        struct.pack_into("<HH", data, 14, len(data), len(data) + 24)
        with self.assertRaisesRegex(ValueError, "track"):
            inspect_payload(data)

    def test_variables_must_fit_their_regions(self):
        for offset, value in ((28, 255), (28, 0), (30, 255), (30, 279)):
            data = sample_payload()
            struct.pack_into("<H", data, offset, value)
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                inspect_payload(data)

    def test_image_keeps_bss_poison_in_sector_padding(self):
        boot = bytes(510) + b"\x55\xaa"
        image = make_image(boot, sample_payload())
        self.assertEqual(len(image), 1_474_560)
        self.assertEqual(image[:512], boot)
        self.assertEqual(image[512:768], sample_payload())
        self.assertEqual(image[768:1024], b"\xa5" * 256)
        self.assertEqual(set(image[1024:]), {0})

    def test_boot_sector_size_and_signature(self):
        for boot in (bytes(512), bytes(511), bytes(511) + b"\x55\xaa"):
            with self.assertRaises(ValueError):
                make_image(boot, sample_payload())


class HostSafetyTests(unittest.TestCase):
    def test_linker_map_checks_every_segment_and_group(self):
        valid = ("_TEXT CODE DGROUP 00000000 00000080\n"
                 "CONST DATA DGROUP 00000080 00000000\n"
                 "CONST2 DATA DGROUP 00000080 00000000\n"
                 "_DATA DATA DGROUP 00000080 00000080\n"
                 "_BSS BSS DGROUP 00000100 00000018\n"
                 "STACK STACK DGROUP 0000e000 00001ffe\n")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "probe.map"
            path.write_text(valid, encoding="utf-8")
            inspect_map(path, inspect_payload(sample_payload()))
            for text in (valid + "foreign BSS OTHER 00010000 00000010\n",
                         valid.replace("_DATA DATA", "_DATA OTHER"),
                         valid.replace("00000000 00000080", "00000000 00000090")):
                path.write_text(text, encoding="utf-8")
                with self.subTest(text=text), self.assertRaises(ValueError):
                    inspect_map(path, inspect_payload(sample_payload()))

    def test_output_refuses_nonregular_entries(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "abi"
            prepare_output(output)
            (output / "abi-probe.img").mkdir()
            with self.assertRaisesRegex(ValueError, "Non-regular"):
                prepare_output(output)

    def test_output_refuses_symlink_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "real").mkdir()
            try:
                (root / "abi").symlink_to(root / "real", target_is_directory=True)
            except OSError:
                self.skipTest("Host does not permit creating symlinks")
            with self.assertRaisesRegex(ValueError, "symlinks"):
                prepare_output(root / "abi")

    def test_checksum_failure_never_modifies_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "compiler"
            path.write_bytes(b"test fixture")
            correct = sha256(path)
            verify(path, correct)
            with self.assertRaisesRegex(ValueError, "Checksum"):
                verify(path, "0" * 64)
            self.assertEqual(path.read_bytes(), b"test fixture")


class BootResultTests(unittest.TestCase):
    def test_success_requires_marker_and_exit_code(self):
        check_result("positive", 33, "RB ABI PASS", 33, "RB ABI PASS")
        for code, log in ((0, "RB ABI PASS"), (33, ""), (33, "FAIL\nRB ABI PASS")):
            with self.subTest(code=code, log=log), self.assertRaises(ValueError):
                check_result("positive", code, log, 33, "RB ABI PASS")

    def test_negative_requires_expected_reason_and_no_success(self):
        check_result("negative", 35, "C BSS FAIL\nRB ABI FAIL", 35, "C BSS FAIL")
        for log in ("RB ABI FAIL", "C BSS FAIL", "C BSS FAIL\nRB ABI FAIL\nRB ABI PASS"):
            with self.subTest(log=log), self.assertRaises(ValueError):
                check_result("negative", 35, log, 35, "C BSS FAIL")


if __name__ == "__main__":
    unittest.main()
