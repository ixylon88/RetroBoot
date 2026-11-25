"""Package the prepared-DOS HDD menu with the local disk-copy tool."""
import argparse
import zipfile

try:
    from .build_hdd import ROOT, SECTOR, fixture
    from .ui_text import LANGUAGES, output_name
except ImportError:
    from build_hdd import ROOT, SECTOR, fixture
    from ui_text import LANGUAGES, output_name


def management_template(parts, language):
    _, extents = fixture(parts, 'retroboot-hdd', language)
    base = int.from_bytes(extents[0][436:440], 'little') * SECTOR
    volume = bytearray(max(at + len(data) for at, data in extents.items()) - base)
    for at, data in extents.items():
        if at >= base:
            volume[at-base:at-base+len(data)] = data
    return volume


def build(language):
    build_dir = ROOT / 'build' / output_name('hdd', language)
    parts = {key: (build_dir / (key + '.bin')).read_bytes() for key in ('mbr', 'vbr', 'bootstrap')}
    parts['stage2'] = (build_dir / 'stage2-dos.bin').read_bytes()
    volume = management_template(parts, language)
    modules = ('prepare_dos_disk', 'prepared_countdown', 'config_records', 'state_records', 'journal_records')
    files = {name+'.py': (ROOT/'tools'/(name+'.py')).read_bytes() for name in modules}
    files.update({'__main__.py': b'from prepare_dos_disk import main\nmain()\n',
                  'mbr.bin': parts['mbr'], 'admin.bin': volume, 'language.txt': language.encode('ascii')})
    kit = build_dir / 'RetroBoot-DOS.pyz'
    with zipfile.ZipFile(kit, 'w') as bundle:
        for name, data in files.items():
            bundle.writestr(zipfile.ZipInfo(name), data, compress_type=zipfile.ZIP_DEFLATED)
    launcher = (ROOT / 'tools/RetroBoot-DOS.cmd').read_text(encoding='ascii').replace('\n', '\r\n')
    archive = build_dir / 'RetroBoot-DOS.zip'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr(zipfile.ZipInfo(kit.name), kit.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
        for name in ('RetroBoot-DOS.cmd', 'RetroBoot-Countdown.cmd'):
            bundle.writestr(zipfile.ZipInfo(name), launcher, compress_type=zipfile.ZIP_DEFLATED)
    return kit


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    print(build(parser.parse_args().language))
