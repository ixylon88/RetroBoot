"""Host arithmetic and CLI regression tests; no guest-OS compatibility claims."""

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.retroboot_layout import LayoutError, chs, fat_geometry, load_plan, validate_plan

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "profiles" / "rb-8g-chs255.json"
CLI = ROOT / "tools" / "retroboot_layout.py"


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.plan = load_plan(REFERENCE)

    def reject(self, expected):
        with self.assertRaisesRegex(LayoutError, expected):
            validate_plan(self.plan)

    def test_reference_matches_phase1_tables(self):
        report = validate_plan(self.plan)
        self.assertEqual(report["disk_bytes"], 8_000_000_000)
        self.assertEqual(report["disk_sectors"], 15_625_000)
        self.assertEqual(report["chs_capacity_sectors"], 16_450_560)
        self.assertEqual(report["trailing_free_sectors"], 9820)
        # Independent fixed expectations from phase 1, not copied from the JSON.
        expected = {
            "P1": (63, 3148739, 193, 49191),
            "P2": (3148740, 6297479, 3075, 392819),
            "P3": (6297480, 10474379, 4079, 521088),
            "L1": (10474443, 11518604, 255, 65226),
            "L2": (11518668, 11647124, 126, 32043),
            "L3": (11647188, 15615179, 3875, 495026),
        }
        for v in report["volumes"]:
            if v["id"] == "P4":
                self.assertEqual((v["start_lba"], v["end_lba"]), (10474380, 15615179))
                self.assertNotIn("fat", v)
            else:
                self.assertEqual((v["start_lba"], v["end_lba"],
                                  v["fat"]["sectors_per_fat"], v["fat"]["data_clusters"]),
                                 expected[v["id"]])

    def test_ebr_relative_bases_are_distinct(self):
        logical = [v for v in validate_plan(self.plan)["volumes"] if v["kind"] == "logical"]
        self.assertEqual([v["ebr_lba"] for v in logical], [10474380, 11518605, 11647125])
        self.assertEqual([v["data_relative_lba"] for v in logical], [63, 63, 63])
        self.assertEqual([v["next_ebr_relative_lba"] for v in logical], [1044225, 1172745, None])

    def test_primary_order_and_names_are_not_fixed(self):
        self.plan["primary"][0], self.plan["primary"][2] = self.plan["primary"][2], self.plan["primary"][0]
        self.plan["primary"][0]["id"] = "My system"
        v = validate_plan(self.plan)["volumes"][0]
        self.assertEqual((v["id"], v["slot"], v["type_hex"]), ("My system", 1, "0B"))

    def test_fewer_systems_and_different_admin_position_are_allowed(self):
        self.plan["primary"] = [self.plan["primary"][1], self.plan["primary"][3]]
        self.plan["logical"] = [self.plan["logical"][1]]
        self.plan["logical"][0]["ebr_lba"] = self.plan["primary"][1]["start_lba"]
        self.assertEqual(len(validate_plan(self.plan)["volumes"]), 3)

    def test_input_is_not_mutated(self):
        original = copy.deepcopy(self.plan)
        validate_plan(self.plan)
        self.assertEqual(self.plan, original)

    def test_primary_overlap(self):
        self.plan["primary"][1]["start_lba"] -= 1
        self.reject("overlap")

    def test_logical_data_overlap(self):
        self.plan["logical"][0]["sectors"] += 100
        self.reject("overlap")

    def test_ebr_inside_another_volume(self):
        self.plan["logical"][1]["ebr_lba"] -= 1
        self.reject("overlap")

    def test_ebr_inside_own_volume(self):
        self.plan["logical"][1]["ebr_lba"] = self.plan["logical"][1]["start_lba"]
        self.reject("precede")

    def test_logical_outside_container(self):
        self.plan["primary"][3]["sectors"] -= 1
        self.reject("outside extended")

    def test_ebr_outside_container(self):
        self.plan["logical"][0]["ebr_lba"] -= 1
        self.reject("outside extended")

    def test_first_ebr_must_match_base(self):
        self.plan["logical"][0]["ebr_lba"] += 1
        self.reject("first EBR")

    def test_duplicate_ebr(self):
        self.plan["logical"][1]["ebr_lba"] = self.plan["logical"][0]["ebr_lba"]
        self.reject("overlap")

    def test_backward_ebr_order(self):
        self.plan["logical"][1:] = reversed(self.plan["logical"][1:])
        self.reject("chain order")

    def test_partition_outside_disk(self):
        self.plan["primary"][3]["sectors"] += 9821
        self.reject("outside disk")

    def test_end_lba_overflow(self):
        self.plan["primary"][0]["start_lba"] = 0xFFFFFFFF
        self.plan["primary"][0]["sectors"] = 2
        self.reject("32-bit LBA overflow")

    def test_fifth_primary_entry(self):
        self.plan["primary"].append(copy.deepcopy(self.plan["primary"][0]))
        self.reject("one to four")

    def test_duplicate_id(self):
        self.plan["logical"][0]["id"] = "P1"
        self.reject("duplicate id")

    def test_multiple_extended_containers(self):
        self.plan["primary"][0] = {"id": "other", "role": "extended", "type": 5,
                                   "start_lba": 63, "sectors": 3148677}
        self.reject("exactly one extended")

    def test_missing_extended(self):
        self.plan["primary"].pop()
        self.reject("exactly one extended")

    def test_empty_logical(self):
        self.plan["logical"] = []
        self.reject("at least")

    def test_visible_admin_volume(self):
        self.plan["logical"][1]["type"] = 6
        self.reject("hidden FAT16")

    def test_missing_or_duplicate_admin(self):
        self.plan["logical"][1]["role"] = "shared"
        self.reject("exactly one logical RetroBoot")
        self.plan["logical"][1]["role"] = "retroboot"
        self.plan["logical"][0].update(role="retroboot", type=22)
        self.reject("exactly one logical RetroBoot")

    def test_no_admin_primary(self):
        self.plan["primary"][0]["role"] = "retroboot"
        self.reject("unsupported primary role")

    def test_unknown_partition_type(self):
        self.plan["primary"][0]["type"] = 0xEE
        self.reject("unsupported partition type")

    def test_lba_extended_not_supported_in_chs_profile(self):
        self.plan["primary"][3]["type"] = 0x0F
        self.reject("05h")

    def test_mismatched_fat_type(self):
        self.plan["primary"][0]["fat"]["bits"] = 32
        self.reject("disagree")

    def test_fat_on_extended_container(self):
        self.plan["primary"][3]["fat"] = {"bits": 16, "sectors_per_cluster": 64}
        self.reject("has no FAT")

    def test_no_guessing_missing_fat(self):
        del self.plan["primary"][0]["fat"]
        self.reject("FAT parameters required")

    def test_geometry_rejects_8gib_and_16_head_bios(self):
        self.plan["disk_bytes"] = 8 * 1024 ** 3
        self.reject("outside CHS reach")
        self.plan["disk_bytes"] = 8_000_000_000
        self.plan["geometry"]["heads"] = 16
        self.reject("outside CHS reach")

    def test_invalid_numeric_inputs(self):
        for field, value in (("sector_size", 4096), ("disk_bytes", 8_000_000_001),
                             ("format_version", 2), ("format_version", True)):
            with self.subTest(field=field, value=value):
                plan = copy.deepcopy(self.plan)
                plan[field] = value
                with self.assertRaises(LayoutError):
                    validate_plan(plan)
        for field, value in (("start_lba", 0), ("start_lba", -1), ("sectors", True),
                             ("sectors", 0), ("sectors", "100"), ("type", 6.0)):
            with self.subTest(field=field, value=value):
                plan = copy.deepcopy(self.plan)
                plan["primary"][0][field] = value
                with self.assertRaises(LayoutError):
                    validate_plan(plan)

    def test_unknown_and_missing_fields(self):
        self.plan["geometery"] = {}
        self.reject("unknown fields")
        del self.plan["geometery"]
        del self.plan["geometry"]
        self.reject("missing fields")


class GeometryTests(unittest.TestCase):
    def test_chs_encoding_and_limit(self):
        g = (1024, 255, 63)
        for lba, coordinates, encoded in ((0, (0, 0, 1), "000100"),
                                          (63, (0, 1, 1), "010100"),
                                          (16065, (1, 0, 1), "000101"),
                                          (16450559, (1023, 254, 63), "feffff")):
            v = chs(lba, g)
            self.assertEqual((v["cylinder"], v["head"], v["sector"]), coordinates)
            self.assertEqual(v["encoded_hex"], encoded)
        with self.assertRaises(LayoutError):
            chs(16450560, g)

    def test_fat_size_is_sufficient_and_minimal(self):
        plan = load_plan(REFERENCE)
        for volume in plan["primary"] + plan["logical"]:
            if "fat" not in volume:
                continue
            fat = fat_geometry(volume["sectors"], volume["fat"]["bits"],
                               volume["fat"]["sectors_per_cluster"])
            size = fat["sectors_per_fat"]
            self.assertGreaterEqual(fat["fat_capacity_entries"], fat["data_clusters"] + 2)
            smaller_data = (volume["sectors"] - fat["reserved_sectors"]
                            - fat["root_directory_sectors"] - 2 * (size - 1))
            smaller_clusters = smaller_data // fat["sectors_per_cluster"]
            self.assertLess((size - 1) * 512 // (fat["bits"] // 8), smaller_clusters + 2)

    def test_fat_cluster_boundaries(self):
        # Two FATs, 32 root sectors for FAT16, one sector per cluster.
        for bits, total, expected in ((16, 4150, 4085), (16, 66069, 65524),
                                      (32, 66581, 65525)):
            self.assertEqual(fat_geometry(total, bits, 1)["data_clusters"], expected)
        for bits, total in ((16, 4149), (16, 66070), (32, 66580), (16, 1)):
            with self.subTest(bits=bits, total=total), self.assertRaises(LayoutError):
                fat_geometry(total, bits, 1)

    def test_invalid_cluster_sizes(self):
        for size in (0, -1, 3, 128, True, 4.0):
            with self.subTest(size=size), self.assertRaises(LayoutError):
                fat_geometry(128457, 16, size)

    def test_planned_fat_can_exceed_minimum(self):
        result = fat_geometry(3148740, 32, 8, 3075)
        self.assertEqual(result["minimum_sectors_per_fat"], 3069)
        self.assertEqual(result["sectors_per_fat"], 3075)
        self.assertEqual(result["data_clusters"], 392819)

    def test_too_small_or_excessive_fat_is_rejected(self):
        for size in (3068, 1574354, True, -1):
            with self.subTest(size=size), self.assertRaises(LayoutError):
                fat_geometry(3148740, 32, 8, size)


class CliTests(unittest.TestCase):
    def call(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(CLI), *map(str, args)],
                              capture_output=True, cwd=cwd)

    def test_report_is_reproducible_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            first = self.call(REFERENCE, "--json", cwd=directory)
            second = self.call(REFERENCE, "--json", cwd=directory)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(first.stdout, second.stdout)
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertEqual(json.loads(first.stdout)["status"], "arithmetic-check-only")

    def test_missing_file_and_directory_are_errors(self):
        for path in (ROOT / "does-not-exist.json", ROOT):
            result = self.call(path)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, b"")
            self.assertNotIn(b"Traceback", result.stderr)

    def test_json_is_utf8_even_with_an_ascii_host_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unicode.json"
            plan = load_plan(REFERENCE)
            plan["name"] = "Prüfung 系统"
            path.write_text(json.dumps(plan), encoding="utf-8")
            result = subprocess.run([sys.executable, str(CLI), str(path), "--json"],
                                    capture_output=True,
                                    env={**os.environ, "PYTHONIOENCODING": "ascii"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout.decode("utf-8"))["name"], plan["name"])
            self.assertNotIn(b"\r\n", result.stdout)

    def test_malformed_json_and_schema_fail_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for data in (b"{", b"null", b"[]", b'{"name": "x", "name": "y"}',
                         b"\xff", b'{"format_version": true}'):
                with self.subTest(data=data):
                    path.write_bytes(data)
                    result = self.call(path)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, b"")
                    self.assertNotIn(b"Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
