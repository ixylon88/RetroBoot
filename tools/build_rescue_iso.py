"""Package verified rescue floppies as reproducible BIOS El Torito CDs."""
import argparse
import hashlib
from importlib.metadata import version
import io
import json
from pathlib import Path
import struct
import sys

try:
    from .build_rescue import IMAGE_BYTES
    from .rescue_text import ROOT, LANGUAGES, metadata, output_name
except ImportError:
    from build_rescue import IMAGE_BYTES
    from rescue_text import ROOT, LANGUAGES, metadata, output_name

PYCDLIB_VERSION = '1.22.0'
BLOCK = 2048
NAMES = ('retroboot-rescue', 'retroboot-rescue-demo')
README = b'''RetroBoot Rescue - BIOS CD

Boot this ISO as a CD/DVD in a BIOS VM. No VDI conversion is needed.
The BIOS presents the embedded 1.44 MiB image as floppy A:.
Enter: HDD diagnosis. F4: saved-file check. F5: saved/current HDD comparison.
F6: preliminary backup read plan and complete FAT boot-area checks; no writes.
The demo contains synthetic RBBACKUP.RBB metadata; the normal image does not.
The demo's matching HDD is retroboot-rescue-target-hdd.img, supplied separately.
retroboot-rescue-bad-reference-hdd.img deliberately fails F5 and F6; F4 stays green.
No restore, installation or OS start is provided. EFI boot is unsupported.
Documentation: https://github.com/ixylon88/RetroBoot/tree/historical/docs
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect_iso(data, floppy):
    """Check this package's BIOS routing and exact embedded bytes independently."""
    def require(ok):
        if not ok:
            raise ValueError('Invalid rescue ISO package')

    require(len(data) >= 20 * BLOCK and len(data) % BLOCK == 0)
    pvd = data[16 * BLOCK:17 * BLOCK]
    require(pvd[:7] == b'\x01CD001\x01')
    require(struct.unpack_from('<I', pvd, 80)[0] == len(data) // BLOCK
            == struct.unpack_from('>I', pvd, 84)[0])
    require(pvd[128:132] == b'\x00\x08\x08\x00')
    boot = data[17 * BLOCK:18 * BLOCK]
    require(boot[:7] == b'\x00CD001\x01'
            and boot[7:39] == b'EL TORITO SPECIFICATION'.ljust(32, b'\0')
            and not any(boot[39:71]) and not any(boot[75:]))
    require(data[18 * BLOCK:18 * BLOCK + 7] == b'\xffCD001\x01')
    catalog_lba = struct.unpack_from('<I', boot, 71)[0]
    require(19 <= catalog_lba < len(data) // BLOCK)
    catalog = data[catalog_lba * BLOCK:(catalog_lba + 1) * BLOCK]
    require(catalog[:4] == b'\x01\x00\x00\x00' and catalog[30:32] == b'\x55\xaa'
            and sum(struct.unpack('<16H', catalog[:32])) & 0xFFFF == 0)
    # x86; bootable 1.44 MiB floppy; default 0000:7C00; one initial sector.
    require(catalog[32:40] == b'\x88\x02\x00\x00\x00\x00\x01\x00'
            and not any(catalog[44:]))
    image_lba = struct.unpack_from('<I', catalog, 40)[0]
    require(len(floppy) == IMAGE_BYTES and image_lba > catalog_lba
            and (image_lba * BLOCK + IMAGE_BYTES) <= len(data)
            and data[image_lba * BLOCK:image_lba * BLOCK + IMAGE_BYTES] == floppy)
    return dict(catalog_lba=catalog_lba, image_lba=image_lba,
                platform=0, media_type=2, initial_sectors=1,
                embedded_floppy_sha256=digest(floppy))


def package(floppy):
    """Wrap an unchanged FAT12 image; no boot-info-table patch or guest code."""
    if (len(floppy) != IMAGE_BYTES or floppy[510:512] != b'\x55\xaa'
            or floppy[11:36] != struct.pack('<HBHBHHBHHHII',
                512, 1, 1, 2, 224, 2880, 0xF0, 9, 18, 2, 0, 0)):
        raise ValueError('A standard RetroBoot 1.44 MiB floppy is required')
    try:
        import pycdlib
        from pycdlib import dates
    except ImportError as error:
        raise ValueError('Install tools/requirements-iso.txt to build rescue ISOs') from error
    if version('pycdlib') != PYCDLIB_VERSION:
        raise ValueError('The pinned pycdlib version is required')
    iso = pycdlib.PyCdlib()
    image, readme, result = io.BytesIO(floppy), io.BytesIO(README), io.BytesIO()
    try:
        iso.new(interchange_level=1, sys_ident='RETROBOOT', vol_ident='RETROBOOT_RESCUE',
                preparer_ident_str='RETROBOOT', app_ident_str='RETROBOOT RESCUE')
        iso.add_fp(image, len(floppy), iso_path='/RESCUE.IMG;1')
        iso.add_fp(readme, len(README), iso_path='/README.TXT;1')
        iso.add_eltorito('/RESCUE.IMG;1', bootcatfile='/BOOT.CAT;1',
                        media_name='floppy', platform_id=0, boot_load_seg=0,
                        boot_info_table=False)
        # The pinned library initializes ISO dates from local wall-clock time.
        # Replace its date objects explicitly, without patching process clocks
        # or changing the timezone; no Rock Ridge, Joliet or UDF dates exist.
        date = dates.DirectoryRecordDate()
        date.parse(bytes((80, 1, 1, 0, 0, 0, 0)))
        iso.pvd.root_directory_record().date = date
        for record in iso.list_children(iso_path='/'):
            record.date = date
        for field in ('volume_creation_date', 'volume_effective_date'):
            stamp = dates.VolumeDescriptorDate()
            stamp.parse(b'1980010100000000\0')
            setattr(iso.pvd, field, stamp)
        iso.write_fp(result)
    finally:
        iso.close()
    data = bytearray(result.getvalue())
    if data[16 * BLOCK:16 * BLOCK + 7] != b'\x01CD001\x01':
        raise ValueError('Unexpected ISO primary descriptor')
    # PyCdlib 1.22.0 serializes a fresh modification date regardless of the
    # object's field. Normalize only that ISO9660 PVD field, never boot bytes.
    data[16 * BLOCK + 830:16 * BLOCK + 847] = b'1980010100000000\0'
    data = bytes(data)
    inspect_iso(data, floppy)
    return data


def build(language='en', repeat=False):
    source = ROOT / 'build' / output_name('rescue', language)
    destination = ROOT / 'build' / ('rescue-iso' + ('-de' if language == 'de' else ''))
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['ui'] != metadata(language):
        raise ValueError('Stale rescue language build')
    images = {}
    for name in NAMES:
        raw = (source / (name + '.img')).read_bytes()
        if manifest['artifacts'][name + '.img'] != dict(bytes=len(raw), sha256=digest(raw)):
            raise ValueError('Rescue image differs from its build manifest: ' + name)
        images[name] = raw
    generated, artifacts = {}, {}
    for name, raw in images.items():
        iso = package(raw)
        if repeat and package(raw) != iso:
            raise ValueError('Rescue ISO did not reproduce: ' + name)
        generated[name + '.iso'] = iso
        artifacts[name + '.iso'] = dict(bytes=len(iso), sha256=digest(iso), **inspect_iso(iso, raw))
    # Verify both source images before publishing either generated package.
    for name, raw in images.items():
        if (source / (name + '.img')).read_bytes() != raw:
            raise ValueError('Rescue source changed while packaging')
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in generated.items():
        (destination / name).write_bytes(data)
    info = dict(ui=manifest['ui'], packaging='El Torito 1.44 MiB floppy emulation',
                pycdlib=PYCDLIB_VERSION, timestamp='1980-01-01T00:00:00Z', artifacts=artifacts)
    (destination / 'manifest.json').write_text(json.dumps(info, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(info, indent=2, sort_keys=True))
    return info


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    parser.add_argument('--repeat', action='store_true')
    args = parser.parse_args()
    try:
        build(args.language, args.repeat)
    except (OSError, ValueError, KeyError) as error:
        print('Rescue ISO: ' + str(error), file=sys.stderr)
        sys.exit(1)
