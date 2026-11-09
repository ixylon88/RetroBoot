"""Independent checks of HDD sector layout, FAT chains and result handling."""

import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools.build_hdd import (COMPACT_BYTES, STAGE2_MAX, fixture, layout,
                             patch_mbr, seal_stage2, seal_sum, write_fixture)
from tools.test_hdd import check_bios_route, check_result, check_trace, read_lbas, scenarios


def samples():
    mbr = bytearray(440)
    mbr[432:436] = b"RBM1"
    vbr = bytearray(512)
    struct.pack_into("<HBHBHHBHHHII", vbr, 11,
                     512, 4, 1, 2, 512, 0, 0xF8, 126, 63, 255, 0, 128457)
    vbr[62:66], vbr[510:] = b"RBV1", b"\x55\xaa"
    bootstrap = bytearray(1536)
    bootstrap[:6] = b"\xeb\x1eRBB1"
    struct.pack_into("<H", bootstrap, 6, len(bootstrap))
    stage2 = bytearray(5000)
    stage2[:6] = b"\xeb\x1eRBS1"
    struct.pack_into("<HIIHHH", stage2, 6, 32, 5000, 0, 0x1000, 32, 1)
    stage2[32:] = bytes(index % 251 for index in range(4968))
    return {"mbr": bytes(mbr), "vbr": bytes(vbr),
            "bootstrap": seal_sum(bootstrap, 8), "stage2": seal_stage2(stage2)}


class DiskFormatTests(unittest.TestCase):
    def test_mbr_preserves_signature_reserved_bytes_and_all_slots(self):
        original = bytearray(bytes(range(256)) * 2)
        original[510:] = b"\x55\xaa"
        updated = patch_mbr(original, samples()["mbr"], 11518668)
        self.assertEqual(updated[440:], original[440:])
        self.assertEqual(struct.unpack_from("<I", updated, 436)[0], 11518668)

    def test_reject_wrong_mbr_budget_or_signature(self):
        sector = bytes(510) + b"\x55\xaa"
        code = samples()["mbr"]
        for s, c, lba in ((sector, code + b"x", 126), (bytes(512), code, 126),
                          (sector, code, 0), (sector, code, 1 << 32)):
            with self.subTest(length=len(c), lba=lba), self.assertRaises(ValueError):
                patch_mbr(s, c, lba)

    def test_checksum_covers_entire_sector_and_is_repeatable(self):
        source = bytes(range(256)) * 2
        sealed = seal_sum(source, 72)
        self.assertEqual(sum(struct.unpack("<256H", sealed)) & 0xFFFF, 0)
        self.assertEqual(seal_sum(sealed, 72), sealed)
        self.assertEqual(sealed[:72] + sealed[74:], source[:72] + source[74:])
        for offset in (0, 511):
            damaged = bytearray(sealed)
            damaged[offset] ^= 1
            self.assertNotEqual(sum(struct.unpack("<256H", damaged)) & 0xFFFF, 0)

    def test_checksum_bounds(self):
        for length, offset in ((511, 72), (512, -2), (512, 511), (512, 512)):
            with self.subTest(length=length, offset=offset), self.assertRaises(ValueError):
                seal_sum(bytes(length), offset)

    def test_stage2_crc_and_memory_contract(self):
        data = samples()["stage2"]
        self.assertEqual(struct.unpack_from("<I", data, 12)[0], zlib.crc32(data[32:]))
        for offset in (0, 1, 2, 6, 8, 16, 18, 20):
            bad = bytearray(data)
            bad[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                seal_stage2(bad)
        oversized = data + bytes(STAGE2_MAX)
        with self.assertRaises(ValueError):
            seal_stage2(oversized)

    def test_compact_hidden_logical_volume_and_free_first_track(self):
        size, admin, extents = layout(False)
        self.assertEqual(size, COMPACT_BYTES)
        self.assertEqual((admin["start_lba"], admin["sectors"]), (126, 128457))
        mbr, ebr = extents[0], extents[63 * 512]
        self.assertEqual(mbr[446:494], bytes(48))
        self.assertEqual((mbr[494], mbr[498], ebr[446], ebr[450]), (0, 5, 0, 0x16))
        self.assertEqual(struct.unpack_from("<II", ebr, 454), (63, 128457))
        _, all_extents = fixture(samples(), "hdd-fragmented")
        self.assertFalse(any(512 <= offset < 63 * 512 for offset in all_extents))

    def test_reference_mbr_ebr_addresses_are_from_v02(self):
        size, admin, extents = layout(True)
        self.assertEqual((size, admin["start_lba"]), (8_000_000_000, 11518668))
        mbr = extents[0]
        expected = ((63, 3148677), (3148740, 3148740), (6297480, 4176900), (10474380, 5140800))
        for slot, pair in enumerate(expected):
            self.assertEqual(struct.unpack_from("<II", mbr, 454 + slot * 16), pair)
        for lba, next_relative in ((10474380, 1044225), (11518605, 1172745), (11647125, 0)):
            ebr = extents[lba * 512]
            self.assertEqual(struct.unpack_from("<I", ebr, 454)[0], 63)
            self.assertEqual(struct.unpack_from("<I", ebr, 470)[0], next_relative)
            self.assertEqual(ebr[510:], b"\x55\xaa")

    def test_fragmented_file_reconstructs_exactly_via_fat(self):
        parts = samples()
        _, extents = fixture(parts, "hdd-fragmented")
        fat = extents[127 * 512]
        self.assertEqual(fat, extents[253 * 512])
        root = extents[379 * 512]
        cluster, size = struct.unpack_from("<HI", root, 640 + 26)
        seen, reconstructed = [], b""
        while cluster < 0xFFF8:
            self.assertNotIn(cluster, seen)
            seen.append(cluster)
            reconstructed += extents[(411 + (cluster - 2) * 4) * 512]
            cluster = struct.unpack_from("<H", fat, cluster * 2)[0]
        self.assertEqual(seen, [20, 300, 40])
        self.assertEqual(size, 5000)
        self.assertEqual(reconstructed, parts["stage2"])
        self.assertEqual(root[:11], b"RBBOOT  SYS")
        self.assertEqual(struct.unpack_from("<H", fat, 4)[0], 0xFFFF)
        self.assertEqual(extents[411 * 512], parts["bootstrap"])

    def test_vbr_pointer_and_both_sums(self):
        _, extents = fixture(samples(), "hdd-fragmented")
        vbr, boot = extents[126 * 512], extents[411 * 512]
        self.assertEqual(struct.unpack_from("<IH", vbr, 66), (411, 3))
        self.assertEqual(sum(struct.unpack("<256H", vbr)) & 0xFFFF, 0)
        self.assertEqual(sum(struct.unpack("<768H", boot)) & 0xFFFF, 0)

    def test_boundary_fixture_keeps_payload_and_crosses_both_edges(self):
        parts = samples()
        _, extents = fixture(parts, "hdd-boundaries")
        root, fat = extents[379 * 512], extents[127 * 512]
        self.assertEqual(struct.unpack_from("<H", root, 666)[0], 25)
        self.assertEqual(struct.unpack_from("<H", fat, 50)[0], 151)
        self.assertEqual(struct.unpack_from("<H", fat, 302)[0], 40)
        data = b"".join(extents[lba * 512] for lba in (503, 1007, 563))
        self.assertEqual(data, parts["stage2"])
        self.assertEqual((503 % 63, 1007 % (16 * 63)), (62, 1007))

    def test_sparse_writer_preserves_gaps_and_exact_size(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.img"
            write_fixture(path, 4096, {0: b"MBR", 3072: b"data"})
            data = path.read_bytes()
            self.assertEqual(len(data), 4096)
            self.assertEqual(data[3:3072], bytes(3069))
            self.assertEqual(data[3072:3076], b"data")

    def test_writer_rejects_overlaps_before_opening(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.img"
            path.write_bytes(b"unchanged")
            for extents in ({0: b"abcd", 3: b"ef"}, {4095: b"xx"}, {-1: b"x"}, {0: b""}):
                with self.subTest(extents=extents), self.assertRaises(ValueError):
                    write_fixture(path, 4096, extents)
                self.assertEqual(path.read_bytes(), b"unchanged")


class EvidenceTests(unittest.TestCase):
    def test_bios_trace_requires_real_fallback_and_no_mixed_reads(self):
        self.assertEqual(check_bios_route("@02\n@41\n@48\n@42\n", "EDD"), ["48", "42"])
        self.assertEqual(check_bios_route("@02\n@41\n@08\n@02\n@00\n@02\n", "CHS"),
                         ["08", "02", "00", "02"])
        for log, mode in (("RB HDD PASS", "CHS"), ("@41\n@41\n@08\n", "CHS"),
                          ("@41\n@08\n@42\n", "CHS"), ("@41\n@48\n@02\n", "EDD"),
                          ("@41\n@08\n", "EDD"), ("@41\n@48\n", "CHS")):
            with self.subTest(log=log, mode=mode), self.assertRaises(ValueError):
                check_bios_route(log, mode)

    def test_sector_sequence_retains_order_and_retries(self):
        trace = "".join(f"ide_sector_read sector={n} nsectors=1\n" for n in (0, 126, 483, 483))
        self.assertEqual(read_lbas(trace), [0, 126, 483, 483])
        for invalid in ("", trace.replace("nsectors=1", "nsectors=2")):
            with self.assertRaises(ValueError):
                read_lbas(invalid)

    def test_each_fixture_has_both_routes_and_geometry_failures_are_separate(self):
        cases = scenarios()
        self.assertEqual(len({c.name for c in cases}), len(cases))
        pairs = {}
        for case in cases:
            if case.pair:
                pairs.setdefault(case.pair, set()).add(case.mode)
        self.assertTrue(pairs)
        self.assertTrue(all(modes == {"EDD", "CHS"} for modes in pairs.values()))
        self.assertTrue(any(c.name == "chs-unreachable-vbr" and c.marker == "RB MBR ERROR" for c in cases))
        self.assertTrue(any(c.name == "chs-unreachable-volume" and c.marker == "RB BPB ERROR" for c in cases))

    def test_boot_result_needs_reason_and_exact_exit(self):
        check_result("good", 33, "RB HDD PASS", "RB HDD PASS")
        check_result("bad", 35, "RB CRC ERROR", "RB CRC ERROR")
        for code, text, expected in ((0, "RB HDD PASS", "RB HDD PASS"),
                                     (33, "", "RB HDD PASS"),
                                     (33, "RB CRC ERROR\nRB HDD PASS", "RB HDD PASS"),
                                     (35, "RB CRC ERROR\nStage 2 ready", "RB CRC ERROR")):
            with self.subTest(code=code, text=text), self.assertRaises(ValueError):
                check_result("bad", code, text, expected)

    def test_uninstrumented_image_requires_controlled_stop(self):
        check_result("normal", 0, "RB HDD PASS", "RB HDD PASS", True)
        with self.assertRaises(ValueError):
            check_result("normal", 33, "RB HDD PASS", "RB HDD PASS", True)

    def test_trace_proves_reads_retries_and_no_writes(self):
        trace = "ide_sector_read sector=0 nsectors=1\n" + "ide_sector_read sector=483 nsectors=1\n" * 3
        check_trace(trace, 483, 3)
        check_trace("blk_co_pwritev snapshot initialization\n" + trace, 483, 3)
        for bad in ("", trace + "ide_sector_write sector=10 nsectors=1\n",
                    trace + "blk_co_pwritev req=1\n", trace.replace("483", "484")):
            with self.subTest(trace=bad), self.assertRaises(ValueError):
                check_trace(bad, 483, 3)


if __name__ == "__main__":
    unittest.main()
