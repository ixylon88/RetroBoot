import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tools.build_rescue import fat12_set
from tools.prepare_mbr_target import (FLOPPY_BYTES, PROFILE_CLUSTER, PROFILE_ENTRY, SECTOR, WITNESS_CLUSTER,
                                      WITNESS_ENTRY, WITNESS_START, allocate_profile, fat_link, prepare_pair,
                                      sealed, write_disk_pair, write_pair)


class TargetEnrollmentTest(unittest.TestCase):
    def setUp(self):
        image = bytearray(FLOPPY_BYTES)
        image[PROFILE_ENTRY - 32:PROFILE_ENTRY - 21] = b'RBRESCUEBIN'
        self.blank = allocate_profile(image, fat12_set)
        self.ids = (bytes(range(16)), bytes(range(16, 32)))

    def test_fields_and_bounds(self):
        model, serial = 'M' * 40, 'S' * 20
        disk, carrier = prepare_pair(self.blank, model, serial, (1 << 48) - 1, *self.ids)
        self.assertEqual(disk[:-512], self.blank[:-512])
        self.assertEqual(disk[-512:-404], b'RBTARG01' + self.ids[0] + ((1 << 48)-1).to_bytes(8, 'little')
                         + self.ids[1] + serial.encode() + model.encode())
        self.assertEqual(carrier[:24], b'RBMEDIA1' + self.ids[1])
        self.assertFalse(any(carrier[512:]))
        for m, s, cap, ids in [('M' * 41, serial, 1, self.ids), (model, ' ', 1, self.ids),
                (model, 'X\nY', 1, self.ids), (model, 'Ä', 1, self.ids), (model, serial, 0, self.ids),
                (model, serial, 1 << 48, self.ids), (model, serial, 1, self.ids[:1] * 2),
                (model, serial, 1, (bytes(16), self.ids[1]))]:
            with self.subTest(model=m, serial=s, capacity=cap, ids=ids), self.assertRaises(ValueError):
                prepare_pair(self.blank, m, s, cap, *ids)
        with self.assertRaises(ValueError):
            prepare_pair(disk, model, serial, 1, *self.ids)

    def test_allocation_and_output_are_exclusive(self):
        with self.assertRaises(ValueError):
            allocate_profile(self.blank, fat12_set)
        with tempfile.TemporaryDirectory() as tmp:
            template, archive = (Path(tmp) / n for n in ('blank.img', 'pair.zip'))
            template.write_bytes(self.blank)
            write_pair(template, archive, 'model', 'serial', 10080)
            first = archive.read_bytes()
            with zipfile.ZipFile(archive) as result:
                self.assertEqual(sorted(result.namelist()), ['mbr-original-data.img', 'mbr-target.img'])
                boot = result.read('mbr-target.img')
                self.assertEqual(boot[-512:-504], b'RBTARG02')
                self.assertEqual(boot[-480:-464], result.read('mbr-original-data.img')[8:24])
                ids = {boot[-504:-488], boot[-480:-464], boot[-404:-388]}
                self.assertEqual(len(ids), 3)
                self.assertNotIn(bytes(16), ids)
                self.assertEqual(boot[WITNESS_START + 8:WITNESS_START + 24], boot[-404:-388])
            with self.assertRaises(FileExistsError):
                write_pair(template, archive, 'other', 'different', 123)
            self.assertEqual(first, archive.read_bytes())
            self.assertEqual(self.blank, template.read_bytes())
            other = Path(tmp) / 'other.zip'
            with patch.object(zipfile.ZipFile, 'writestr', side_effect=OSError('interrupted')), self.assertRaises(OSError):
                write_pair(template, other, 'model', 'serial', 10080)
            self.assertFalse(other.exists())

    def test_witness_layout_and_provisioning(self):
        witness = bytes(range(32, 48))
        boot, _ = prepare_pair(self.blank, 'test', 'drive', 35, *self.ids, witness)
        self.assertEqual(boot[WITNESS_ENTRY:WITNESS_ENTRY + 12], b'RBWITNESBIN\x20')
        self.assertEqual(struct.unpack_from('<HI', boot, WITNESS_ENTRY + 26), (WITNESS_CLUSTER, 5 * SECTOR))
        self.assertEqual(boot[WITNESS_START:WITNESS_START + SECTOR], sealed(b'RBMEDIA1' + witness))
        self.assertFalse(any(boot[WITNESS_START + SECTOR:-SECTOR]))
        self.assertEqual(boot[-404:-4], witness + bytes(384))
        self.assertEqual(boot[:-SECTOR][:WITNESS_START], self.blank[:WITNESS_START])
        for start in (SECTOR, 10 * SECTOR):
            fat = boot[start:start + 9 * SECTOR]
            self.assertEqual([fat_link(fat, c) for c in range(WITNESS_CLUSTER, PROFILE_CLUSTER + 1)],
                             [WITNESS_CLUSTER + n for n in range(1, 5)] + [0xfff, 0xfff])
        for invalid in (bytes(16), *self.ids, witness[1:]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                prepare_pair(self.blank, 'test', 'drive', 35, *self.ids, invalid)
        for offset in (WITNESS_ENTRY + 11, WITNESS_ENTRY + 28, WITNESS_START + SECTOR,
                       10 * SECTOR + WITNESS_CLUSTER * 3 // 2):
            damaged = bytearray(self.blank)
            damaged[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                prepare_pair(damaged, 'test', 'drive', 35, *self.ids, witness)

    def test_legacy_template_requires_unallocated_witness_space(self):
        image = bytearray(self.blank)
        image[WITNESS_ENTRY:WITNESS_ENTRY + 32] = bytes(32)
        with tempfile.TemporaryDirectory() as tmp:
            template, output = (Path(tmp) / name for name in ('template.img', 'pair.zip'))
            template.write_bytes(image)
            with self.assertRaises(ValueError):
                write_pair(template, output, 'old', 'disk', 10080)
            self.assertFalse(output.exists())
            fat = image[SECTOR:10 * SECTOR]
            for c in range(WITNESS_CLUSTER, PROFILE_CLUSTER):
                fat12_set(fat, c, 0)
            image[SECTOR:10 * SECTOR] = image[10 * SECTOR:19 * SECTOR] = fat
            template.write_bytes(image)
            write_pair(template, output, 'old', 'disk', 10080)
            with zipfile.ZipFile(output) as result:
                boot = result.read('mbr-target.img')
                self.assertEqual(boot[-512:-504], b'RBTARG01')
                self.assertEqual(boot[:-512], image[:-512])


    def test_second_disk_enrollment_and_new_sparse_output(self):
        current = self.blank[:3] + b'RBTARG03' + self.blank[11:]
        witness = bytes(range(32, 48))
        rec = ('disk', 'second', 10080)
        boot, label = prepare_pair(current, 'disk', 'first', 10080, *self.ids, witness, recovery=rec)
        self.assertEqual(boot[-512:-504], b'RBTARG03')
        self.assertEqual(boot[-388:-320], b'second'.ljust(20) + b'disk'.ljust(40) + struct.pack('<Q', 10080))
        self.assertEqual(boot[-320:-4], bytes(316))
        self.assertEqual(label, sealed(b'RBMEDIA1' + self.ids[1]))
        for template, w, recovery in ((self.blank, witness, rec), (current, None, rec),
                (current, witness, ('disk', 'first ', 10081)), (current, witness, ('disk', 'other', 6)),
                (current, witness, ('disk', 'other', 1 << 48))):
            with self.subTest(recovery=recovery), self.assertRaises(ValueError):
                prepare_pair(template, 'disk', 'first', 10080, *self.ids, w, recovery=recovery)
        with tempfile.TemporaryDirectory() as tmp:
            template, output = Path(tmp) / 'blank.img', Path(tmp) / 'pair'
            template.write_bytes(current)
            write_disk_pair(template, output, 'disk', 'first', 10080, rec)
            actual = (output / 'mbr-target.img').read_bytes()
            raw = (output / 'mbr-recovery.img').read_bytes()
            self.assertEqual(len(raw), 10080 * SECTOR)
            self.assertEqual(raw[:SECTOR], sealed(b'RBMEDIA1' + actual[-480:-464]))
            self.assertFalse(any(raw[SECTOR:]))
            with self.assertRaises(FileExistsError):
                write_disk_pair(template, output, 'other', 'disk', 99, rec)
            self.assertEqual((output / 'mbr-target.img').read_bytes(), actual)
            self.assertEqual(template.read_bytes(), current)
