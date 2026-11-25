import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from test_hdd_tools import samples
from tools import config_records, prepared_countdown, prepared_install_state, prepared_records
from tools.build_dos_kit import management_template

from tools.prepare_dos_disk import SECTOR, dos_volume, make_disk, read_sector, set_vdi_geometry, write_disk_copy


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

    def prepared_image(self, directory):
        source, kit, image = (directory / name for name in ('dos.img', 'data.zip', 'prepared.img'))
        source.write_bytes(self.source())
        parts = samples()
        with zipfile.ZipFile(kit, 'w') as archive:
            archive.writestr('mbr.bin', parts['mbr'])
            archive.writestr('admin.bin', management_template(parts, 'de'))
            archive.writestr('language.txt', 'de')
        make_disk(source, image, kit, 10)
        return image

    def test_countdown_alternates_one_sector_and_same_value_is_a_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = self.prepared_image(Path(tmp))
            for seconds, active, generation in ((0, 1, 2), (60, 0, 3), (60, 0, 3)):
                output = Path(tmp) / f'copy-{seconds}-{image.stem}.img'
                write_disk_copy(image, output, lambda disk: prepared_countdown.change_countdown(disk, seconds, 'en'))
                with image.open('rb') as a, output.open('rb') as b:
                    before, after = prepared_countdown.inspect(a), prepared_countdown.inspect(b)
                    self.assertEqual(after.active, active)
                    new = after.copies[active]
                    self.assertEqual(struct.unpack_from('<I', new, 16)[0], generation)
                    self.assertEqual(struct.unpack_from('<H', new, 38)[0], seconds)
                    self.assertEqual(after.copies[1-active], before.copies[1-active])
                    expected = bytearray(before.copies[before.active])
                    struct.pack_into('<I', expected, 16, generation)
                    struct.pack_into('<H', expected, 38, seconds)
                    self.assertEqual(new, config_records.seal(expected))
                    # Compare every byte outside the one published sector, including DOS.
                    pos = after.lbas[active] * SECTOR
                    a.seek(0)
                    b.seek(0)
                    while a.tell() < pos:
                        length = min(1024 * 1024, pos - a.tell())
                        self.assertEqual(a.read(length), b.read(length))
                    a.seek(SECTOR, 1)
                    b.seek(SECTOR, 1)
                    self.assertEqual(hashlib.file_digest(a, 'sha256').digest(),
                                     hashlib.file_digest(b, 'sha256').digest())
                    if after.active == before.active:
                        self.assertEqual(after, before)
                image = output

    def test_damaged_or_ambiguous_records_and_allocations_block_prepared_writers(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = self.prepared_image(Path(tmp))
            with image.open('r+b') as disk:
                before = prepared_countdown.inspect(disk)
                a, b = (lba * SECTOR for lba in before.lbas)
                admin = struct.unpack_from('<I', read_sector(disk, 0), 436)[0]
                vbr = read_sector(disk, admin)
                spf = struct.unpack_from('<H', vbr, 22)[0]
                files = prepared_countdown.management_files(disk, admin, struct.unpack_from('<I', vbr, 32)[0])
                first = bytearray(before.copies[0])
                def reseal(offset, fmt, value):
                    cfg = first.copy()
                    struct.pack_into(fmt, cfg, offset, value)
                    return config_records.seal(cfg)
                fat = (admin + 1) * SECTOR
                root = (admin + 1 + 2 * spf) * SECTOR
                max_gen = reseal(16, '<I', 0xffffffff)
                cases = {
                    'crc': [(b + 508, bytes([first[508] ^ 1]))],
                    'torn countdown': [(b, reseal(16, '<I', 2)[:24])],
                    'equal generation conflict': [(b, reseal(38, '<H', 11))],
                    'stale peer': [(b, reseal(16, '<I', 4))],
                    'generation exhausted': [(a, max_gen), (b, max_gen)],
                    'other installation': [(b, reseal(108, '<Q', 0))],
                    'legacy version': [(b, reseal(8, '<H', 1))],
                    'two bad checksums': [(a + 508, bytes([first[508] ^ 1])), (b + 509, bytes([first[509] ^ 1]))],
                    'torn identity': [(b + 48, bytes([first[48] ^ 1]))],
                    'out-of-range sealed timer': [(b, reseal(38, '<H', 61))],
                    'pending state': [(files[n][0] * SECTOR + 83, b'\x02') for n in prepared_countdown.STATE],
                    'journal': [(files[prepared_countdown.JOURNAL[1]][0] * SECTOR, b'?')],
                    'changed DOS VBR': [(63 * SECTOR + 509, b'\x01')],
                    'fat mirror': [(fat + 2, b'\x00')],
                    'orphan in both fats': [(fat + copy * spf * SECTOR + 8000, b'\xff\xff') for copy in (0,1)],
                    'overlapping files': [(root + 22*32 + 26, struct.pack('<H', config_records.CLUSTERS[0]))],
                    'foreign disk': [(440, b'\x00\x00\x00\x00')],
                }
                for name, changes in cases.items():
                    with self.subTest(name=name):
                        saved = []
                        for pos, data in changes:
                            disk.seek(pos)
                            saved.append((pos, disk.read(len(data))))
                            disk.seek(pos)
                            disk.write(data)
                        with self.assertRaises(ValueError):
                            prepared_countdown.change_countdown(disk, 1, 'de')
                        if name == 'generation exhausted':
                            # Config and installation counters are independent.
                            self.assertFalse(prepared_install_state.inspect_state(disk)[3])
                        else:
                            with patch('builtins.input', side_effect=AssertionError('unexpected prompt')), self.assertRaises(ValueError):
                                prepared_install_state.require_recovery(disk, 'de')
                        if name not in ('crc', 'torn countdown', 'generation exhausted'):
                            with patch('builtins.input', side_effect=AssertionError('unexpected prompt')), self.assertRaises(ValueError):
                                prepared_countdown.recover_countdown(disk, 'de')
                        for pos, data in saved:
                            disk.seek(pos)
                            disk.write(data)
                        self.assertEqual(prepared_countdown.inspect(disk), before)

    def test_cancel_and_torn_readback_publish_nothing_and_allow_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = self.prepared_image(Path(tmp))
            output = Path(tmp) / 'updated.img'
            with original.open('rb') as disk:
                before = prepared_countdown.inspect(disk)
                disk.seek(0)
                original_hash = hashlib.file_digest(disk, 'sha256').digest()

            def change(disk):
                return prepared_countdown.change_countdown(disk, 0, 'de')

            def damage_write(fd):
                os.lseek(fd, before.lbas[1] * SECTOR + 16, os.SEEK_SET)
                os.write(fd, before.copies[1][16:20])

            with patch('builtins.input', return_value=''), self.assertRaisesRegex(ValueError, 'Abgebrochen'):
                write_disk_copy(original, output, lambda disk: prepared_countdown.change_countdown(disk, None, 'de'))
            self.assertFalse(output.exists())
            with patch('tools.prepared_records.os.fsync', side_effect=damage_write), self.assertRaises(ValueError):
                write_disk_copy(original, output, change)
            self.assertFalse(output.exists())
            with patch('tools.prepared_records.os.fsync', side_effect=OSError('flush')), self.assertRaises(OSError):
                write_disk_copy(original, output, change)
            self.assertFalse(output.exists())
            write_disk_copy(original, output, change)
            with original.open('rb') as disk:
                self.assertEqual(hashlib.file_digest(disk, 'sha256').digest(), original_hash)
            with self.assertRaises(FileExistsError):
                write_disk_copy(original, output, change)

    def test_countdown_recovery_keeps_survivor_for_both_slot_orders_and_every_torn_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.prepared_image(Path(tmp)).open('r+b') as disk:
                original = prepared_countdown.inspect(disk)
                def sector(generation, seconds):
                    record = bytearray(original.copies[0])
                    struct.pack_into('<I', record, 16, generation)
                    struct.pack_into('<H', record, 38, seconds)
                    return config_records.seal(record)

                old, survivor, intended = sector(254, 10), sector(255, 0), sector(256, 60)
                torn = {intended[:cut] + old[cut:] for cut in range(SECTOR + 1)} - {old, intended}
                self.assertGreater(len(torn), 2)
                for target in (0, 1):
                    disk.seek(original.lbas[1 - target] * SECTOR)
                    disk.write(survivor)
                    for partial in torn:
                        with self.subTest(target=target, partial_crc=partial[-4:]):
                            disk.seek(original.lbas[target] * SECTOR)
                            disk.write(partial)
                            with patch('builtins.input', return_value='J'):
                                prepared_countdown.recover_countdown(disk, 'de')
                            after = prepared_countdown.inspect(disk)
                            self.assertEqual(after.copies, (survivor, survivor))
                            self.assertEqual(after.active, 0)

                # Restoring redundancy at the generation ceiling needs no increment.
                last = sector(0xffffffff, 10)
                disk.seek(original.lbas[0] * SECTOR)
                disk.write(last)
                disk.seek(original.lbas[1] * SECTOR)
                disk.write(last[:508] + bytes(4))
                with patch('builtins.input', return_value='y'):
                    prepared_countdown.recover_countdown(disk, 'en')
                self.assertEqual(prepared_countdown.inspect(disk).copies, (last, last))

    def test_countdown_recovery_rechecks_consent_readback_and_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = self.prepared_image(Path(tmp))
            output = Path(tmp) / 'recovered.img'
            def recover(disk):
                return prepared_countdown.recover_countdown(disk, 'en')

            with image.open('r+b') as disk:
                prepared_countdown.change_countdown(disk, 0, 'en')
                before = prepared_countdown.inspect(disk)
                with patch('builtins.input', side_effect=AssertionError('healthy peers need no repair')):
                    self.assertFalse(write_disk_copy(image, output, recover))
                self.assertFalse(output.exists())
                bad_lba = before.lbas[0]
                disk.seek(bad_lba * SECTOR + 16)
                disk.write(struct.pack('<I', 3))
            with image.open('rb') as disk:
                broken_hash = hashlib.file_digest(disk, 'sha256').digest()

            for reply in ('', 'n', 'j'):
                with patch('builtins.input', return_value=reply), self.assertRaisesRegex(ValueError, 'Cancelled'):
                    write_disk_copy(image, output, recover)
                self.assertFalse(output.exists())
            with patch('builtins.input', side_effect=EOFError), self.assertRaisesRegex(ValueError, 'Cancelled'):
                write_disk_copy(image, output, recover)
            self.assertFalse(output.exists())

            def changed_while_waiting(disk):
                def consent(_prompt):
                    disk.seek(bad_lba * SECTOR + 16)
                    disk.write(struct.pack('<I', 4))
                    return 'y'
                with patch('builtins.input', side_effect=consent):
                    return recover(disk)
            with self.assertRaisesRegex(ValueError, 'changed before the update'):
                write_disk_copy(image, output, changed_while_waiting)
            self.assertFalse(output.exists())

            def failed_readback(fd):
                os.lseek(fd, before.lbas[1] * SECTOR, os.SEEK_SET)
                os.write(fd, before.copies[0])
            with patch('builtins.input', return_value='Y'):
                with patch('tools.prepared_records.os.fsync', side_effect=OSError('flush')), self.assertRaises(OSError):
                    write_disk_copy(image, output, recover)
                self.assertFalse(output.exists())
                with patch('tools.prepared_records.os.fsync', side_effect=failed_readback), self.assertRaisesRegex(ValueError, 'readback'):
                    write_disk_copy(image, output, recover)
                self.assertFalse(output.exists())
                self.assertTrue(write_disk_copy(image, output, recover))
            with image.open('rb') as disk:
                self.assertEqual(hashlib.file_digest(disk, 'sha256').digest(), broken_hash)
            with output.open('r+b') as disk:
                self.assertEqual(prepared_countdown.inspect(disk).copies, (before.copies[1], before.copies[1]))
                prepared_countdown.change_countdown(disk, 1, 'en')
                self.assertEqual(prepared_countdown.inspect(disk).active, 1)

    def test_installation_hold_is_one_sector_and_preserves_edited_countdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.prepared_image(Path(tmp))
            result = Path(tmp) / 'blocked.img'
            with source.open('r+b') as disk:
                prepared_countdown.change_countdown(disk, 19, 'en')
                disk.seek(0)
                original = hashlib.file_digest(disk, 'sha256').digest()
                records, _, _, _ = prepared_install_state.inspect_state(disk)
            with patch('builtins.input', return_value='Y'):
                written = write_disk_copy(source, result, lambda f: prepared_install_state.require_recovery(f, 'en'))
            self.assertTrue(written)
            expected = bytearray(records.state[0])
            struct.pack_into('<I', expected, 16, 2)
            expected[83:88] = b'\x07\0\0\0\0'
            expected = config_records.seal(expected)
            a, b = (records.files[name][0] for name in prepared_records.STATE)
            with source.open('rb') as src, result.open('r+b') as disk:
                self.assertEqual(hashlib.file_digest(src, 'sha256').digest(), original)
                after, _, slot, damaged = prepared_install_state.inspect_state(disk)
                self.assertEqual((after.state, slot, damaged), ((records.state[0], expected), 1, False))
                self.assertEqual(after.config, records.config)
                self.assertEqual(read_sector(disk, a), records.state[0])
                with patch('builtins.input', side_effect=AssertionError('healthy hold is a no-op')):
                    self.assertIsNone(prepared_install_state.require_recovery(disk, 'en'))
                # Replacing just B with its original bytes reconstructs the entire source.
                disk.seek(b * SECTOR)
                disk.write(records.state[1])
                disk.seek(0)
                self.assertEqual(hashlib.file_digest(disk, 'sha256').digest(), original)

    def test_torn_installation_hold_reaches_recovery_for_every_prefix_and_both_slots(self):
        with tempfile.TemporaryDirectory() as tmp, self.prepared_image(Path(tmp)).open('r+b') as disk:
            before, _, _, _ = prepared_install_state.inspect_state(disk)
            lbas = [before.files[name][0] for name in prepared_records.STATE]

            def record(generation, phase):
                data = bytearray(before.state[0])
                struct.pack_into('<I', data, 16, generation)
                data[83] = phase
                if phase == 7:
                    data[84:88] = bytes(4)
                return config_records.seal(data)

            old, survivor, intended = record(254, 6), record(255, 6), record(256, 7)
            # Different cut positions producing the same sector need one physical run.
            prefixes = {intended[:cut] + old[cut:] for cut in range(SECTOR + 1)}
            self.assertGreater(len(prefixes), 4)
            for target in (0, 1):
                disk.seek(lbas[1 - target] * SECTOR)
                disk.write(survivor)
                for partial in prefixes:
                    with self.subTest(target=target, crc=partial[-4:]), patch('builtins.input', return_value='J'):
                        disk.seek(lbas[target] * SECTOR)
                        disk.write(partial)
                        prepared_install_state.require_recovery(disk, 'de')
                        after, _, active, damaged = prepared_install_state.inspect_state(disk)
                        self.assertEqual((active, damaged), (target, False))
                        self.assertEqual(after.state[target], intended)
                        self.assertEqual(after.state[1 - target], survivor)
            # A damaged peer of a surviving hold can be restored at maximum generation.
            last = record(0xffffffff, 7)
            for lba, raw in zip(lbas, (last, last[:508] + bytes(4))):
                disk.seek(lba * SECTOR)
                disk.write(raw)
            with patch('builtins.input', return_value='y'):
                prepared_install_state.require_recovery(disk, 'en')
            after, _, active, damaged = prepared_install_state.inspect_state(disk)
            self.assertEqual((after.state, active, damaged), ((last, last), 0, False))

    def test_torn_verification_boot_can_only_reinstate_the_hold(self):
        with tempfile.TemporaryDirectory() as tmp, self.prepared_image(Path(tmp)).open('r+b') as disk:
            before, _, _, _ = prepared_install_state.inspect_state(disk)
            lbas = [before.files[name][0] for name in prepared_records.STATE]
            def record(generation, phase):
                raw = bytearray(before.state[0])
                struct.pack_into('<I', raw, 16, generation)
                raw[83] = phase
                if phase != 6:
                    raw[84:88] = bytes(4)
                return config_records.seal(raw)

            ready, held, pending, reheld = record(254, 6), record(255, 7), record(256, 5), record(257, 7)
            cuts = {pending[:cut] + ready[cut:] for cut in range(SECTOR + 1)}
            for target in (0, 1):
                for partial in cuts:
                    with self.subTest(target=target, crc=partial[-4:]), patch('builtins.input', return_value='y'):
                        for index, contents in ((1 - target, held), (target, partial)):
                            disk.seek(lbas[index] * SECTOR)
                            disk.write(contents)
                        result = prepared_install_state.require_recovery(disk, 'en')
                        after, _, active, damaged = prepared_install_state.inspect_state(disk)
                        self.assertFalse(damaged)
                        if partial == ready:
                            self.assertIsNone(result)
                            self.assertEqual((after.state[target], after.state[active]), (ready, held))
                        elif partial == pending:
                            self.assertEqual((after.state[target], after.state[active]), (pending, reheld))
                        else:
                            self.assertEqual(after.state, (held, held))
            # A verified, surviving pending record can return to recovery even
            # if its adjacent hold was subsequently damaged.
            for index, contents in enumerate((pending, held[:508] + bytes(4))):
                disk.seek(lbas[index] * SECTOR)
                disk.write(contents)
            with patch('builtins.input', return_value='y'):
                prepared_install_state.require_recovery(disk, 'en')
            after, _, active, damaged = prepared_install_state.inspect_state(disk)
            self.assertEqual((after.state, active, damaged), ((pending, reheld), 1, False))

    def test_installation_write_rejects_wrong_binding_history_and_generation_limit(self):
        with tempfile.TemporaryDirectory() as tmp, self.prepared_image(Path(tmp)).open('r+b') as disk:
            before, _, _, _ = prepared_install_state.inspect_state(disk)
            ready = before.state[0]

            def edit(offset, data, source=ready, seal=True):
                changed = bytearray(source)
                changed[offset:offset + len(data)] = data
                return config_records.seal(changed) if seal else bytes(changed)

            recovery = edit(83, b'\x07' + bytes(4))
            damaged = edit(508, bytes(4), seal=False)
            max_ready = edit(16, b'\xff' * 4)
            pending = edit(83, b'\x05' + bytes(4))
            cases = {
                'direct ready to pending': (ready, edit(16, struct.pack('<I', 2), pending)),
                'pending to ready': (pending, edit(16, struct.pack('<I', 2))),
                'full pending': (edit(16, struct.pack('<I', 0xfffffffe), recovery),
                                 edit(16, struct.pack('<I', 0xffffffff), pending)),
                'conflict': (ready, recovery),
                'gap': (ready, edit(16, struct.pack('<I', 3))),
                'reverse': (recovery, edit(16, struct.pack('<I', 2))),
                'phase': (edit(83, b'\x05' + bytes(4)),) * 2,
                'different installation': (edit(64, bytes(8)),) * 2,
                'wrong ready VBR': (edit(84, bytes(4)),) * 2,
                'foreign damaged peer': (ready, edit(64, bytes(8), damaged, False)),
                'damaged layout': (ready, edit(24, bytes(4), damaged, False)),
                'two damaged': (damaged, damaged),
                'full': (max_ready, max_ready),
            }
            a, b = (before.files[n][0] for n in prepared_records.STATE)
            for name, pair in cases.items():
                for lba, data in zip((a, b), pair):
                    disk.seek(lba * SECTOR)
                    disk.write(data)
                with self.subTest(case=name), patch('builtins.input', side_effect=AssertionError('invalid review')):
                    with self.assertRaises(ValueError):
                        prepared_install_state.require_recovery(disk, 'en')
                    self.assertEqual((read_sector(disk, a), read_sector(disk, b)), pair)

    def test_installation_publication_requires_fresh_consent_flush_and_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.prepared_image(Path(tmp))
            result = Path(tmp) / 'blocked.img'
            with source.open('rb') as disk:
                original = hashlib.file_digest(disk, 'sha256').digest()
                records, _, _, _ = prepared_install_state.inspect_state(disk)
                admin = records.binding['admin_start']
                root = admin + 1 + 2 * struct.unpack_from('<H', read_sector(disk, admin), 22)[0]
            target = records.files[prepared_records.STATE[1]][0]
            def hold(disk):
                return prepared_install_state.require_recovery(disk, 'de')

            for reply in ('', 'n', 'y'):
                with patch('builtins.input', return_value=reply), self.assertRaisesRegex(ValueError, 'Abgebrochen'):
                    write_disk_copy(source, result, hold)
                self.assertFalse(result.exists())
            with patch('builtins.input', side_effect=EOFError), self.assertRaisesRegex(ValueError, 'Abgebrochen'):
                write_disk_copy(source, result, hold)

            def changed(disk):
                def consent(_):
                    disk.seek(root * SECTOR + 22)  # Valid directory timestamp, same allocation.
                    disk.write(b'\x01')
                    return 'j'
                with patch('builtins.input', side_effect=consent):
                    return hold(disk)
            with self.assertRaisesRegex(ValueError, 'changed before'):
                write_disk_copy(source, result, changed)
            def restore_target(fd):
                os.lseek(fd, target * SECTOR, os.SEEK_SET)
                os.write(fd, records.state[1])
            for fault in (OSError('flush'), restore_target):
                with patch('builtins.input', return_value='j'), patch('tools.prepared_records.os.fsync', side_effect=fault):
                    with self.assertRaises((OSError, ValueError)):
                        write_disk_copy(source, result, hold)
                self.assertFalse(result.exists())
            with source.open('rb') as disk:
                self.assertEqual(hashlib.file_digest(disk, 'sha256').digest(), original)

    def approval_images(self, directory, generation=1, trial_slot=0):
        # Construct the pre-trial reference and its descendant independently of
        # the approval writer. Keep the original VBR claim in the READY record.
        ready = self.prepared_image(directory)
        with ready.open('rb') as stream:
            records = prepared_records.read_records(stream)
        lbas = [records.files[name][0] for name in prepared_records.STATE]

        def sector(number, phase):
            data = bytearray(records.state[0])
            struct.pack_into('<I', data, 16, number)
            data[83] = phase
            if phase != 6:
                data[84:88] = bytes(4)
            return config_records.seal(data)

        prior = sector(generation, 6)
        hold = sector(generation + 1, 7)
        pending = sector(generation + 2, 5)
        reference, trial = directory / 'reference.img', directory / 'trial.img'
        with ready.open('r+b') as stream:
            for lba in lbas:
                stream.seek(lba * SECTOR)
                stream.write(prior)
        shutil.copyfile(ready, reference)
        with reference.open('r+b') as stream:
            stream.seek(lbas[1 - trial_slot] * SECTOR)
            stream.write(hold)
        shutil.copyfile(reference, trial)
        with trial.open('r+b') as stream:
            stream.seek(lbas[trial_slot] * SECTOR)
            stream.write(pending)
        return ready, reference, trial, lbas, sector

    def test_approval_binds_both_slots_repeats_and_recovers_the_existing_countdown(self):
        for slot, pre_hold, generation in ((0, False, 1), (1, False, 253), (0, True, 0xfffffffc)):
            with self.subTest(slot=slot, initial=generation), tempfile.TemporaryDirectory() as tmp:
                ready, held, trial, lbas, sector = self.approval_images(Path(tmp), generation, slot)
                approved = Path(tmp) / 'approved.img'
                reference = ready if pre_hold else held
                with reference.open('rb') as proof, patch('builtins.input', return_value='J'):
                    self.assertTrue(write_disk_copy(trial, approved,
                        lambda disk: prepared_install_state.confirm_verification(disk, proof, 'de')))
                    with approved.open('r+b') as disk, patch('builtins.input', side_effect=AssertionError('no extra consent')):
                        state, _, selected, damaged = prepared_install_state.inspect_state(disk)
                        self.assertEqual((state.state, selected, damaged), ((sector(generation + 3, 6),) * 2, 0, False))
                        self.assertIsNone(prepared_install_state.confirm_verification(disk, proof, 'en'))
                        prepared_countdown.change_countdown(disk, 2, 'en')
                        self.assertEqual(prepared_countdown.inspect(disk).copies[1][38], 2)
                with trial.open('rb') as original:
                    self.assertEqual(read_sector(original, lbas[slot]), sector(generation + 2, 5))
                    self.assertEqual(read_sector(original, lbas[1 - slot]), sector(generation + 1, 7))

    def test_approval_refuses_stale_foreign_damaged_or_unconsumed_inputs_before_consent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, reference, trial, lbas, sector = self.approval_images(root)
            with trial.open('rb') as source:
                records = prepared_records.read_records(source)
            cfg = bytearray(records.config[1])
            struct.pack_into('<I', cfg, 16, 2)
            cfg[38] = 1
            cases = (
                (trial, records.target['start'], 509, b'\x17'),
                (trial, lbas[0], 0, sector(1, 6)),        # Hold never consumed.
                (trial, lbas[1], 0, sector(4, 7)),        # Trial already returned to recovery.
                (trial, lbas[1], 508, bytes(4)),
                (reference, lbas[0], 508, bytes(4)),
                (reference, lbas[0], 0, sector(2, 7)),    # No independent READY evidence.
                (reference, lbas[0], 0, sector(3, 5)),    # Pending disk as reference.
                (trial, records.files[prepared_records.CONFIG[1]][0], 0, config_records.seal(cfg)),
                (reference, records.files[prepared_records.JOURNAL[0]][0], 508, bytes(4)),
            )
            with patch('builtins.input', side_effect=AssertionError('unexpected consent')):
                for path, lba, offset, data in cases:
                    with self.subTest(path=path.name, lba=lba, offset=offset):
                        with path.open('r+b') as disk:
                            original = read_sector(disk, lba)
                            disk.seek(lba * SECTOR + offset)
                            disk.write(data)
                        with trial.open('r+b') as tested, reference.open('rb') as proof, self.assertRaises(ValueError):
                            prepared_install_state.confirm_verification(tested, proof, 'de')
                        with path.open('r+b') as disk:
                            disk.seek(lba * SECTOR)
                            disk.write(original)
                separate = root / 'separate'
                separate.mkdir()
                _, foreign, _, _, _ = self.approval_images(separate)
                with trial.open('r+b') as tested, foreign.open('rb') as proof, self.assertRaises(ValueError):
                    prepared_install_state.confirm_verification(tested, proof, 'en')
                full = root / 'full'
                full.mkdir()
                _, ref_full, last_trial, _, _ = self.approval_images(full, 0xfffffffd)
                with last_trial.open('r+b') as tested, ref_full.open('rb') as proof, self.assertRaisesRegex(ValueError, 'exhausted'):
                    prepared_install_state.confirm_verification(tested, proof, 'en')

    def test_approval_publication_requires_observation_and_each_independent_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, reference, trial, lbas, _ = self.approval_images(root)
            output = root / 'approved.img'
            with trial.open('rb') as disk:
                original_hash = hashlib.file_digest(disk, 'sha256').digest()
            with reference.open('rb') as proof:
                def approve(disk):
                    return prepared_install_state.confirm_verification(disk, proof, 'de')

                for reply in ('', 'n', 'Y', 'yes'):
                    with patch('builtins.input', return_value=reply), self.assertRaisesRegex(ValueError, 'Abgebrochen'):
                        write_disk_copy(trial, output, approve)
                    self.assertFalse(output.exists())
                with patch('builtins.input', side_effect=EOFError), self.assertRaisesRegex(ValueError, 'Abgebrochen'):
                    write_disk_copy(trial, output, approve)

                with trial.open('rb') as stream:
                    records = prepared_records.read_records(stream)
                admin = records.binding['admin_start']
                directory_lba = admin + 1 + 2 * struct.unpack_from('<H', read_sector(proof, admin), 22)[0]
                def change_directory(disk):
                    disk.seek(directory_lba * SECTOR + 22)
                    disk.write(b'\x17')
                    disk.flush()

                def stale(disk):
                    def reply(_):
                        change_directory(disk)
                        return 'J'
                    with patch('builtins.input', side_effect=reply):
                        return approve(disk)
                with self.assertRaisesRegex(ValueError, 'changed before'):
                    write_disk_copy(trial, output, stale)

                for target, failure in ((1, 'write'), (0, 'write'), (1, 'readback'), (0, 'readback'), (0, 'fsync')):
                    writes = []
                    def inject(disk, lba, contents):
                        writes.append(lba)
                        if lba != lbas[target]:
                            return prepared_records.write_sector(disk, lba, contents)
                        if failure == 'write':
                            raise OSError('write')
                        if failure == 'fsync':
                            with patch('tools.prepared_records.os.fsync', side_effect=OSError('flush')):
                                return prepared_records.write_sector(disk, lba, contents)
                        # Simulate a successful write whose sector still contains the old data.
                    with self.subTest(target=target, fault=failure), patch('builtins.input', return_value='J'):
                        with patch.object(prepared_install_state, 'write_sector', side_effect=inject):
                            with self.assertRaises((ValueError, OSError)):
                                write_disk_copy(trial, output, approve)
                        self.assertEqual(writes, [lbas[1]] if target == 1 else [lbas[1], lbas[0]])
                        self.assertFalse(output.exists())

                def create_competing_output(_):
                    output.write_bytes(b'existing output')
                    return 'J'
                with patch('builtins.input', side_effect=create_competing_output), self.assertRaises(FileExistsError):
                    write_disk_copy(trial, output, approve)
                self.assertEqual(output.read_bytes(), b'existing output')
                output.unlink()

                original_directory = read_sector(proof, directory_lba)
                for changed_slot in (1, 0):
                    def change_reference(disk, lba, data):
                        prepared_records.write_sector(disk, lba, data)
                        if lba == lbas[changed_slot]:
                            with reference.open('r+b') as other:
                                change_directory(other)
                    with patch('builtins.input', return_value='J'), patch.object(prepared_install_state, 'write_sector',
                            side_effect=change_reference) as writer, self.assertRaisesRegex(ValueError, 'Reference changed'):
                        write_disk_copy(trial, output, approve)
                    self.assertEqual(writer.call_count, 1 if changed_slot == 1 else 2)
                    self.assertFalse(output.exists())
                    with reference.open('r+b') as other:
                        other.seek(directory_lba * SECTOR)
                        other.write(original_directory)
            with trial.open('rb') as disk:
                self.assertEqual(hashlib.file_digest(disk, 'sha256').digest(), original_hash)

    def test_external_hold_after_every_distinct_torn_approval_sector(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, reference, trial, lbas, sector = self.approval_images(Path(tmp), 253)
            hold, pending, final = sector(254, 7), sector(255, 5), sector(256, 6)
            with trial.open('r+b') as disk, reference.open('rb') as proof:
                for mirror in (False, True):
                    target, previous, survivor = (0, pending, final) if mirror else (1, hold, pending)
                    cuts = {final[:cut] + previous[cut:] for cut in range(SECTOR + 1)}
                    for partial in cuts:
                        for slot, value in ((target, partial), (1 - target, survivor)):
                            disk.seek(lbas[slot] * SECTOR)
                            disk.write(value)
                        if partial not in (previous, final):
                            with self.assertRaises(ValueError), patch('builtins.input', side_effect=AssertionError('torn approval')):
                                prepared_install_state.confirm_verification(disk, proof, 'en')
                        with patch('builtins.input', return_value='Y'):
                            prepared_install_state.require_recovery(disk, 'en')
                        after, _, active, damaged = prepared_install_state.inspect_state(disk)
                        self.assertFalse(damaged)
                        self.assertEqual(after.state[active][83], 7)

    @unittest.skipUnless(os.name == 'nt', 'Windows drag-and-drop launcher')
    def test_windows_approval_launcher_passes_both_quoted_input_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            launcher = root / 'RetroBoot-Confirm-Verification.cmd'
            shutil.copyfile(Path(__file__).resolve().parents[1] / 'tools/RetroBoot-DOS.cmd', launcher)
            (root / 'RetroBoot-DOS.pyz').write_text('import json, sys\nprint(json.dumps(sys.argv[1:]))\n')
            source = root / 'observed & tested!.vdi'
            source.touch()
            for supplied in (False, True):
                reference = root / ('reference with spaces.img' if supplied else 'RetroBoot-Reference.img')
                reference.touch()
                args = [os.environ['COMSPEC'], '/d', '/c', launcher.name, source.name]
                if supplied:
                    args.append(reference.name)
                result = subprocess.run(args, cwd=root, input='\n', text=True, capture_output=True, check=True)
                actual = next(json.loads(line) for line in result.stdout.splitlines() if line.startswith('['))
                self.assertEqual(actual, [str(source), '--confirm-verification', str(reference),
                                          '--output', str(root / 'RetroBoot-DOS-Ready.vdi')])
