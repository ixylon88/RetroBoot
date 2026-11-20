import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tools.build_rescue import fat12_set
from tools.prepare_mbr_target import allocate_profile, prepare_pair, write_pair, FLOPPY_BYTES, PROFILE_ENTRY


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
                self.assertEqual(result.read('mbr-target.img')[-480:-464], result.read('mbr-original-data.img')[8:24])
            with self.assertRaises(FileExistsError):
                write_pair(template, archive, 'other', 'different', 123)
            self.assertEqual(first, archive.read_bytes())
            self.assertEqual(self.blank, template.read_bytes())
            other = Path(tmp) / 'other.zip'
            with patch.object(zipfile.ZipFile, 'writestr', side_effect=OSError('interrupted')), self.assertRaises(OSError):
                write_pair(template, other, 'model', 'serial', 10080)
            self.assertFalse(other.exists())
