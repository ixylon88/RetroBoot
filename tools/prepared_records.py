"""Live layout, owned file extents and records on a prepared DOS disk copy."""
from dataclasses import dataclass
import hashlib
import os
import struct
import zlib

try:
    from . import config_records, journal_records
    from .prepare_dos_disk import SECTOR, dos_volume, dword, partition, read_sector, word
except ImportError:
    import config_records
    import journal_records
    from prepare_dos_disk import SECTOR, dos_volume, dword, partition, read_sector, word


CONFIG = (b'RBCFG   A  ', b'RBCFG   B  ')
STATE = (b'RBSTATE A  ', b'RBSTATE B  ')
JOURNAL = (b'RBTXN   A  ', b'RBTXN   B  ')
BOOT, STAGE2 = b'RBBOOT  SYS', b'RBSTG2  BIN'
SIZES = {BOOT: 8192, STAGE2: 49152, **dict.fromkeys(CONFIG + STATE, SECTOR),
         **dict.fromkeys(JOURNAL, journal_records.BYTES)}


def sectors(stream, lba, count):
    stream.seek(lba * SECTOR)
    data = stream.read(count * SECTOR)
    if len(data) != count * SECTOR:
        raise ValueError('Incomplete management volume')
    return data


def _management_allocation(disk, start, length):
    """Map the eight closed-format files after checking both FATs and every allocation."""
    vbr = read_sector(disk, start)
    spc, spf = vbr[13], word(vbr, 22)
    root = start + 1 + 2 * spf
    data = root + 32
    if (vbr[62:66] != b'RBV1' or vbr[510:] != b'\x55\xaa' or word(vbr, 11) != SECTOR
            or not 1 <= spc <= 64 or spc & (spc - 1) or word(vbr, 14) != 1 or vbr[16] != 2
            or word(vbr, 17) != 512 or word(vbr, 19) or vbr[21] != 0xf8 or not 1 <= spf <= 256
            or dword(vbr, 28) != start or dword(vbr, 32) != length
            or sum(struct.unpack('<256H', vbr)) & 0xffff):
        raise ValueError('Invalid RetroBoot management boot sector')
    clusters = (start + length - data) // spc
    if not 4085 <= clusters <= min(0xffee, spf * 256 - 2):
        raise ValueError('Invalid management FAT16 extent')
    fat = sectors(disk, start + 1, spf)
    if fat[:4] != b'\xf8\xff\xff\xff' or fat != sectors(disk, start + 1 + spf, spf):
        raise ValueError('Management FAT copies differ or have invalid headers')

    owned, files = set(), {}
    directory = sectors(disk, root, 32)
    for offset in range(0, len(directory), 32):
        row = directory[offset:offset + 32]
        if not row[0]:
            break
        if row[0] == 0xe5:
            continue
        name, cluster, size = row[:11], word(row, 26), dword(row, 28)
        if row[11] == 8 and not (word(row, 20) or cluster or size):
            continue
        if (name not in SIZES or name in files or row[11] & 0xd8 or word(row, 20)
                or not 0 < size <= SIZES[name] or (name == BOOT and size % SECTOR)
                or (name not in (BOOT, STAGE2) and size != SIZES[name])):
            raise ValueError('Unknown, duplicate or invalid management file')
        lbas = []
        required = (size + SECTOR - 1) // SECTOR
        while len(lbas) < required:
            if not 2 <= cluster <= clusters + 1 or cluster in owned:
                raise ValueError('Invalid or shared management cluster')
            owned.add(cluster)
            first = data + (cluster - 2) * spc
            lbas.extend(range(first, first + min(spc, required - len(lbas))))
            cluster = word(fat, 2 * cluster)
        if cluster < 0xfff8:
            raise ValueError('Management chain extends beyond its file')
        files[name] = tuple(lbas)
    if files.keys() != SIZES.keys():
        raise ValueError('Missing management file')
    if files[BOOT] != tuple(range(dword(vbr, 66), dword(vbr, 66) + word(vbr, 70))):
        raise ValueError('Bootstrap extent disagrees with its directory allocation')
    if any(word(fat, 2 * i) for i in range(2, clusters + 2) if i not in owned):
        raise ValueError('Unowned management cluster')
    return files, hashlib.sha256(vbr + fat + directory).digest()


def management_files(disk, start, length):
    return _management_allocation(disk, start, length)[0]


@dataclass(frozen=True)
class PreparedRecords:
    geometry: tuple
    binding: dict
    target: dict
    mbr: bytes
    ebr: bytes
    vbr: bytes
    files: dict
    allocation: bytes
    config: tuple
    state: tuple


def read_records(disk):
    size = disk.seek(0, os.SEEK_END)
    mbr, slot, start, length, vbr = dos_volume(disk, size, prepared=True)
    spt, heads = struct.unpack_from('<HH', vbr, 24)
    admin, disk_id = struct.unpack_from('<II', mbr, 436)
    offset = 446 + (3 if slot != 3 else 2) * 16
    ebr_lba, extent = struct.unpack_from('<II', mbr, offset + 8)
    count = extent - spt
    if (mbr[432:436] != b'RBM1' or not disk_id or ebr_lba < start + length
            or admin != ebr_lba + spt or count <= 0 or admin + count > size // SECTOR
            or mbr[offset:offset + 16] != partition(5, ebr_lba, extent, ebr_lba, heads, spt)):
        raise ValueError('Invalid prepared DOS management extent')
    ebr = read_sector(disk, ebr_lba)
    if ebr != bytes(446) + partition(0x16, admin, count, spt, heads, spt) + bytes(48) + b'\x55\xaa':
        raise ValueError('Unexpected management partition table')
    files, allocation = _management_allocation(disk, admin, count)

    def record(name):
        return b''.join(read_sector(disk, lba) for lba in files[name])

    journals = tuple(record(name) for name in JOURNAL)
    binding = dict(disk_id=disk_id, layout=config_records.layout_crc({0: mbr, ebr_lba * SECTOR: ebr}),
                   admin_start=admin, admin_sectors=count, media_id=journals[0][48:64])
    baseline = journal_records.encode(**binding, sequence=1, phase=journal_records.EMPTY,
                                      capacity=size // SECTOR, before=mbr, after=mbr)
    if journals != (baseline, baseline):
        raise ValueError('Prepared DOS journal is outside the idle baseline')
    return PreparedRecords((size // SECTOR, heads, spt), binding,
        dict(slot=slot + 1, type=6, start=start, sectors=length), mbr, ebr, vbr, files,
        allocation, tuple(record(name) for name in CONFIG), tuple(record(name) for name in STATE))


def select_generation(copies, family):
    a, b = copies
    ga, gb = dword(a, 16), dword(b, 16)
    if abs(ga - gb) > 1 or (ga == gb and a != b):
        raise ValueError(f'Ambiguous or stale {family} pair')
    return int(gb > ga)


def check_configuration(copies, binding, entry, *, allow_damage=False):
    a, b = copies
    bad_crc = [index for index, cfg in enumerate(copies) if dword(cfg, 508) != zlib.crc32(cfg[:508])]
    if len(bad_crc) == 2:
        raise ValueError('Both configuration checksums failed')
    if bad_crc and not allow_damage:
        raise ValueError('A configuration checksum failed')
    # A countdown update can change only the generation, delay and checksum.
    # In particular, never use a damaged slot to infer an identity or a profile.
    if a[:16] != b[:16] or a[20:38] != b[20:38] or a[40:508] != b[40:508]:
        raise ValueError('Configuration copies differ outside the countdown fields')
    for index, cfg in enumerate(copies):
        if index in bad_crc:
            continue
        # Re-encoding with the live layout and independent installation ID also
        # verifies all reserved bytes, bounds, approval flags and the stored CRC.
        profile = dict(entry, id=dword(cfg, 64), installed=2, approved=1,
                       name=cfg[84:84 + cfg[82]].decode('cp437'))
        expected = config_records.encode(**binding, profiles=[profile], default_id=profile['id'],
            countdown=word(cfg, 38), generation=dword(cfg, 16), language='de' if cfg[44] else 'en')
        if cfg != expected:
            raise ValueError('Configuration differs from the live prepared DOS installation')
    if bad_crc:
        return 1 - bad_crc[0], True
    return select_generation(copies, 'configuration'), False


def write_sector(disk, lba, sector):
    """Write one audited sector on the caller's private raw copy."""
    if len(sector) != SECTOR:
        raise ValueError('Expected one complete record')
    disk.seek(lba * SECTOR)
    if disk.write(sector) != SECTOR:
        raise OSError('Incomplete record write')
    disk.flush()
    os.fsync(disk.fileno())
