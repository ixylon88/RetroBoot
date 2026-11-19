import io
from pathlib import Path
import struct
import tempfile
import unittest

from tools.prepare_dos_disk import SECTOR, dos_volume, make_disk, set_vdi_geometry


class PreparedDiskTests(unittest.TestCase):
    def source(self):
        start, count = 63, 5073
        image = bytearray((start + count) * SECTOR)
        image[446], image[450] = 0x80, 6
        struct.pack_into('<II', image, 454, start, count)
        image[510:512] = b'\x55\xaa'
        boot = memoryview(image)[start * SECTOR:(start+1) * SECTOR]
        boot[:3] = b'\xeb\x3c\x90'
        struct.pack_into('<HBHBHHBHHHII', boot, 11, 512, 1, 1, 2, 512, count,
                         0xf8, 20, 63, 16, start, 0)
        boot[510:] = b'\x55\xaa'
        root = (start+41)*SECTOR
        for i, name in enumerate((b'IO      SYS', b'MSDOS   SYS', b'COMMAND COM')):
            at = root+32*i
            image[at:at+11] = name
            struct.pack_into('<HI', image, at+26, 2+i, 512)
        return image

    def test_requires_a_bootable_single_dos_volume(self):
        image = self.source()
        self.assertEqual(dos_volume(io.BytesIO(image), len(image))[1:4], (0,63,5073))
        for offset, value in ((510,0), (446,0), (466,5), (63*SECTOR+28,1),
                              (63*SECTOR+24,0), (104*SECTOR+64,0xe5)):
            with self.subTest(offset=offset):
                damaged = bytearray(image)
                damaged[offset] = value
                with self.assertRaises(ValueError):
                    dos_volume(io.BytesIO(damaged), len(damaged))

    def test_existing_output_and_invalid_media_are_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'source.img', Path(tmp)/'out.img'
            source.write_bytes(b'bad input')
            output.write_bytes(b'existing')
            with self.assertRaises(FileExistsError):
                make_disk(source, output, Path(tmp)/'absent.pyz', 0)
            self.assertEqual(output.read_bytes(), b'existing')
            output.unlink()
            with self.assertRaises(ValueError):
                make_disk(source, output, Path(tmp)/'absent.pyz', 0)
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), b'bad input')

    def test_only_logical_geometry_changes_in_new_vdi(self):
        sectors, heads, spt = 262144, 16, 63
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'new.vdi'
            header = bytearray(512)
            struct.pack_into('<IIII', header, 64, 0xbeda107f, 0x10001, 400, 1)
            struct.pack_into('<I', header, 340, 1048576)
            struct.pack_into('<Q', header, 368, sectors * 512)
            struct.pack_into('<I', header, 468, 512)
            path.write_bytes(header)
            set_vdi_geometry(path, sectors, heads, spt)
            struct.pack_into('<III', header, 456, sectors//(heads*spt), heads, spt)
            self.assertEqual(path.read_bytes(), header)
            with self.assertRaises(ValueError):
                set_vdi_geometry(path, sectors+1, heads, spt)
            self.assertEqual(path.read_bytes(), header)
