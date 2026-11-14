"""Independent El Torito fields, ISO directory mapping and unchanged boot bytes."""
import contextlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tools import build_rescue_iso as cd
from tools.build_rescue import make_image
from tools.rescue_text import metadata
from tests.test_rescue_tools import boot, payload


class RescueIsoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.floppy = make_image(boot(), payload(30001))
        cls.iso = cd.package(cls.floppy)

    def test_catalog_routes_bios_to_an_unchanged_floppy(self):
        data = self.iso
        pvd = 16 * 2048
        catalog = struct.unpack_from('<I', data, 17 * 2048 + 71)[0] * 2048
        self.assertEqual(data[pvd:pvd + 7], b'\x01CD001\x01')
        self.assertEqual(data[pvd + 40:pvd + 72].rstrip(), b'RETROBOOT_RESCUE')
        self.assertEqual(data[catalog:catalog + 4], b'\x01\x00\x00\x00')
        self.assertEqual(data[catalog + 30:catalog + 40], b'\x55\xaa\x88\x02\0\0\0\0\x01\0')
        self.assertEqual(sum(struct.unpack_from('<16H', data, catalog)) & 65535, 0)
        image = struct.unpack_from('<I', data, catalog + 40)[0] * 2048
        self.assertEqual(data[image:image + 1474560], self.floppy)
        self.assertEqual(data[image:image + 512], boot())
        self.assertEqual(data[18 * 2048:18 * 2048 + 7], b'\xffCD001\x01')

    def test_directory_files_and_dates_are_consistent(self):
        data = self.iso; pvd = 16 * 2048
        root = struct.unpack_from('<I', data, pvd + 158)[0] * 2048
        size = struct.unpack_from('<I', data, pvd + 166)[0]
        records = {}; cursor = root
        while cursor < root + size and data[cursor]:
            length = data[cursor]
            lba, count = struct.unpack_from('<I', data, cursor + 2)[0], struct.unpack_from('<I', data, cursor + 10)[0]
            self.assertEqual(lba, struct.unpack_from('>I', data, cursor + 6)[0])
            self.assertEqual(count, struct.unpack_from('>I', data, cursor + 14)[0])
            self.assertEqual(data[cursor + 18:cursor + 25], bytes((80, 1, 1, 0, 0, 0, 0)))
            name = data[cursor + 33:cursor + 33 + data[cursor + 32]]
            records[name] = (lba, count); cursor += length
        self.assertEqual(set(records), {b'\0', b'\x01', b'BOOT.CAT;1', b'README.TXT;1', b'RESCUE.IMG;1'})
        for name, expected in ((b'RESCUE.IMG;1', self.floppy), (b'README.TXT;1', cd.README)):
            lba, count = records[name]
            self.assertEqual(data[lba * 2048:lba * 2048 + count], expected)
        catalog = struct.unpack_from('<I', data, 17 * 2048 + 71)[0]
        self.assertEqual(records[b'BOOT.CAT;1'], (catalog, 2048))
        self.assertEqual(struct.unpack_from('<I', data, catalog * 2048 + 40)[0], records[b'RESCUE.IMG;1'][0])
        for offset in (813, 830, 864):
            self.assertEqual(data[pvd + offset:pvd + offset + 17], b'1980010100000000\0')

    def test_wall_clock_and_timezone_do_not_change_output(self):
        for timestamp, offset in ((946684800, -32), (1893456000, 36)):
            with patch('time.time', return_value=timestamp), patch('pycdlib.utils.gmtoffset_from_tm', return_value=offset):
                self.assertEqual(cd.package(self.floppy), self.iso)

    def test_wrong_floppy_sizes_geometry_or_signature_are_rejected(self):
        bad = bytearray(self.floppy); bad[24] = 17
        signature = bytearray(self.floppy); signature[510] = 0
        for raw in (b'', self.floppy[:-1], self.floppy + b'\0', bytes(bad), bytes(signature)):
            with self.assertRaises(ValueError): cd.package(raw)

    def test_package_checker_rejects_routing_bounds_and_payload_damage(self):
        catalog = struct.unpack_from('<I', self.iso, 17 * 2048 + 71)[0] * 2048
        image = struct.unpack_from('<I', self.iso, catalog + 40)[0] * 2048
        for at in (16 * 2048 + 80, 17 * 2048 + 71, catalog + 1, catalog + 28,
                   catalog + 32, catalog + 33, catalog + 34, catalog + 38,
                   catalog + 40, image, image + len(self.floppy) - 1):
            data = bytearray(self.iso); data[at] ^= 1
            with self.assertRaises(ValueError): cd.inspect_iso(data, self.floppy)
        for data in (self.iso[:-1], self.iso[:20 * 2048]):
            with self.assertRaises(ValueError): cd.inspect_iso(data, self.floppy)

    def test_published_inputs_are_verified_and_repeat_builds_match(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(cd, 'ROOT', Path(temp)), contextlib.redirect_stdout(io.StringIO()):
            source = Path(temp) / 'build/rescue'; source.mkdir(parents=True)
            manifest = dict(ui=metadata('en'), artifacts={})
            for name in cd.NAMES:
                (source / (name + '.img')).write_bytes(self.floppy)
                manifest['artifacts'][name + '.img'] = dict(bytes=len(self.floppy), sha256=cd.digest(self.floppy))
            path = source / 'manifest.json'; path.write_text(json.dumps(manifest))
            first = cd.build(repeat=True)
            self.assertEqual(first, cd.build(repeat=True))
            output = Path(temp) / 'build/rescue-iso/retroboot-rescue-demo.iso'
            self.assertEqual(output.read_bytes(), self.iso)
            (source / 'retroboot-rescue-demo.img').write_bytes(self.floppy[:-1])
            with self.assertRaises(ValueError): cd.build()
            self.assertEqual(output.read_bytes(), self.iso)
            manifest['ui']['language'] = 'de'; path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): cd.build()


if __name__ == '__main__': unittest.main()
