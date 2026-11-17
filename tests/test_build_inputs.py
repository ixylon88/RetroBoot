"""Stale source trees must not authorize rescue tests or packaging."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.build_inputs import source_hashes, check_build_inputs
from tools import test_rescue, test_rescue_match, test_rescue_plan


class BuildInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.header = self.root / 'include/backup_stream.h'
        self.header.parent.mkdir()
        self.header.write_bytes(b'typedef char size_check[16];\n')
        self.manifest = dict(build_inputs=source_hashes(self.root))

    def test_snapshot_uses_relative_paths_and_content_only(self):
        expected = {'include/backup_stream.h': hashlib.sha256(self.header.read_bytes()).hexdigest()}
        self.assertEqual(self.manifest['build_inputs'], expected)
        for name in ('docs/notes.md', 'build/model.bin', 'tools/__pycache__/cache.pyc'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'unrelated')
        os.utime(self.header, (1, 1))
        check_build_inputs(self.manifest, self.root)
        other = self.root / 'another-checkout'
        (other / 'include').mkdir(parents=True)
        (other / 'include/backup_stream.h').write_bytes(self.header.read_bytes())
        self.assertEqual(source_hashes(other), expected)

    def test_changed_header_is_rejected_even_with_same_size_and_timestamp(self):
        original = self.header.read_bytes()
        stat = self.header.stat()
        self.header.write_bytes(original.replace(b'16', b'17'))
        os.utime(self.header, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, 'Stale rescue build inputs'):
            check_build_inputs(self.manifest, self.root)
        self.header.write_bytes(original)
        check_build_inputs(self.manifest, self.root)

    def test_added_deleted_and_unrecorded_inputs_are_rejected(self):
        added = self.header.with_name('new.h')
        added.write_bytes(b'new source')
        with self.assertRaises(ValueError): check_build_inputs(self.manifest, self.root)
        added.unlink()
        with self.assertRaises(ValueError): check_build_inputs({}, self.root)
        self.header.unlink()
        with self.assertRaises(ValueError): check_build_inputs(self.manifest, self.root)
        with self.assertRaises(ValueError): check_build_inputs(dict(build_inputs={}), self.root)

    def test_rescue_campaigns_reject_stale_inputs_before_starting_qemu(self):
        source = self.root / 'build/rescue'
        source.mkdir(parents=True)
        (source / 'manifest.json').write_text(json.dumps(self.manifest))
        self.header.write_bytes(b'changed after build')
        for module in (test_rescue, test_rescue_match, test_rescue_plan):
            with self.subTest(campaign=module.__name__), \
                    patch.object(module, 'ROOT', self.root), \
                    patch.object(module, 'prepare_output', lambda p: p.mkdir(exist_ok=True)), \
                    patch.object(module.sys, 'argv', ['campaign']), \
                    patch.object(module.shutil, 'which', return_value=str(self.root / 'qemu')), \
                    patch.object(module.subprocess, 'Popen') as start:
                with self.assertRaisesRegex(ValueError, 'Stale rescue build inputs'):
                    module.main()
                start.assert_not_called()


if __name__ == '__main__': unittest.main()
