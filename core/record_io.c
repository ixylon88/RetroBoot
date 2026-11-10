#include "record_io.h"

typedef struct {
    rb_sector_reader read;
    void *opaque;
    rb_u32 at;
    rb_u8 sector[512];
} capture;

static rb_u16 word(const rb_u8 *p)
{
    return p[0] | ((rb_u16)p[1] << 8);
}

static rb_u32 dword(const rb_u8 *p)
{
    return (rb_u32)word(p) | ((rb_u32)word(p + 2) << 16);
}

static rb_u16 __cdecl captured_read(rb_u32 lba, rb_u8 *sector, void *opaque)
{
    capture *c = (capture *)opaque;
    rb_u16 i, code = c->read(lba, sector, c->opaque);
    if (code == 0 && lba == c->at) {
        for (i = 0; i < 512; ++i) { c->sector[i] = sector[i]; }
    }
    return code;
}

static void fail(rb_record_files *r, rb_u16 status, rb_u16 detail, rb_u32 lba)
{
    rb_u16 i;
    rb_u8 *p = (rb_u8 *)r;
    for (i = 0; i < sizeof(*r); ++i) { p[i] = 0; }
    r->status = status; r->detail = detail; r->error_lba = lba;
    r->copies[0] = status; r->copies[1] = status;
}

void rb_record_read(rb_record_files *r, rb_u16 family, rb_sector_reader read, void *opaque,
                    rb_u32 low, rb_u32 high, rb_u32 disk_id, rb_u32 admin_lba)
{
    rb_partition *admin = (rb_partition *)0;
    rb_volume_probe volume;
    capture c;
    rb_u8 sector[512];
    const rb_u8 names[4][11] = {{'R','B','C','F','G',' ',' ',' ','A',' ',' '},
                               {'R','B','C','F','G',' ',' ',' ','B',' ',' '},
                               {'R','B','S','T','A','T','E',' ','A',' ',' '},
                               {'R','B','S','T','A','T','E',' ','B',' ',' '}};
    rb_u8 *entry;
    rb_u16 clusters[4] = {0, 0, 0, 0}, base = family * 2, at;
    rb_u16 i, j, k, copy, match, done = 0, previous = 0, value, spc;
    rb_u32 root, fat, lba;
    fail(r, RB_CONFIG_OK, 0, 0);
    r->copies[0] = r->copies[1] = RB_CONFIG_MISSING;
    if (family > RB_FILES_STATE) { fail(r, RB_CONFIG_FORMAT, 0, 0); return; }
    c.read = read; c.opaque = opaque; c.at = 0;
    rb_scan_partitions(&r->scan, captured_read, &c, low, high, disk_id);
    if (r->scan.status != 0) { fail(r, RB_CONFIG_SCAN, r->scan.status, r->scan.error_lba); return; }
    if (c.sector[432] != 'R' || c.sector[433] != 'B' || c.sector[434] != 'M'
            || c.sector[435] != '1' || dword(c.sector + 436) != admin_lba) {
        fail(r, RB_CONFIG_ADMIN, 0, 0); return;
    }
    for (i = 4; i < r->scan.count; ++i) {
        if (r->scan.entries[i].start == admin_lba && (r->scan.entries[i].type == 0x16
                || r->scan.entries[i].type == 0x1E)) { admin = &r->scan.entries[i]; }
    }
    if (admin == (rb_partition *)0) { fail(r, RB_CONFIG_ADMIN, 0, admin_lba); return; }
    r->admin = *admin;
    c.at = admin_lba;
    rb_probe_volume(&volume, admin, captured_read, &c, low, high);
    if (volume.status != 0) { fail(r, RB_CONFIG_ADMIN, volume.status, admin_lba); return; }
    if (volume.fat_bits != 16 || volume.fats != 2 || word(c.sector + 14) != 1
            || word(c.sector + 17) != 512 || volume.total_sectors != admin->sectors) {
        fail(r, RB_CONFIG_ADMIN, 0, admin_lba); return;
    }
    fat = admin_lba + 1; root = fat + 2 * volume.fat_sectors;
    spc = volume.cluster_bytes / 512;
    for (i = 0; i < 32 && !done; ++i) {
        if (read(root + i, sector, opaque)) { fail(r, RB_CONFIG_IO, 0, root + i); return; }
        for (j = 0; j < 16; ++j) {
            entry = sector + j * 32;
            if (entry[0] == 0) { done = 1; break; }
            if (entry[0] == 0xE5 || entry[11] == 0x0F) { continue; }
            for (copy = 0; copy < 4; ++copy) {
                match = 1;
                for (k = 0; k < 11; ++k) { if (entry[k] != names[copy][k]) { match = 0; } }
                if (!match) { continue; }
                value = word(entry + 26);
                if (clusters[copy] != 0 || (entry[11] & 0xD8U) || word(entry + 20) != 0
                        || dword(entry + 28) != 512 || value < 2 || value >= 0xFFF0U
                        || (rb_u32)value >= volume.clusters + 2) {
                    fail(r, RB_CONFIG_DIRECTORY, copy, root + i); return;
                }
                clusters[copy] = value;
            }
        }
    }
    for (i = 0; i < 4; ++i) {
        for (j = 0; j < i; ++j) {
            if (clusters[i] && clusters[i] == clusters[j]) { fail(r, RB_CONFIG_DIRECTORY, 4, root); return; }
        }
    }
    for (copy = 0; copy < 2; ++copy) {
        at = base + copy;
        if (clusters[at] == 0) { continue; }
        for (i = 0; i < 2; ++i) {
            lba = fat + i * volume.fat_sectors + clusters[at] / 256;
            if (read(lba, sector, opaque)) { fail(r, RB_CONFIG_IO, 0, lba); return; }
            value = word(sector + (clusters[at] % 256) * 2);
            if (value < 0xFFF8U || (i && value != previous)) { fail(r, RB_CONFIG_FAT, copy, lba); return; }
            previous = value;
        }
        lba = volume.data_lba + ((rb_u32)clusters[at] - 2) * spc;
        r->file_lba[copy] = lba;
        if (read(lba, r->records[copy], opaque)) { r->copies[copy] = RB_CONFIG_IO; r->error_lba = lba; }
        else { r->mask |= 1U << copy; r->copies[copy] = RB_CONFIG_OK; }
    }
}
