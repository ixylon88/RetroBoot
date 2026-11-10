#include "config.h"

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

static void fail(rb_config_result *r, rb_u16 status, rb_u16 detail, rb_u32 lba)
{
    rb_u16 i;
    rb_u8 *p = (rb_u8 *)r;
    for (i = 0; i < sizeof(*r); ++i) { p[i] = 0; }
    r->source = RB_CONFIG_NONE; r->status = status; r->detail = detail; r->error_lba = lba;
    r->copies[0] = status; r->copies[1] = status;
}

void rb_config_load(rb_config_result *r, rb_sector_reader read, void *opaque,
                    rb_u32 low, rb_u32 high, rb_u32 disk_id, rb_u32 admin_lba)
{
    rb_partition_scan scan;
    rb_partition *admin = (rb_partition *)0;
    rb_volume_probe volume;
    capture c;
    rb_u8 sector[512], records[2][512];
    const rb_u8 names[2][11] = {{'R','B','C','F','G',' ',' ',' ','A',' ',' '},
                               {'R','B','C','F','G',' ',' ',' ','B',' ',' '}};
    rb_u8 *entry;
    rb_u16 clusters[2] = {0, 0}, mask = 0, io_mask = 0;
    rb_u16 i, j, k, copy, match, done = 0, previous = 0, value, spc;
    rb_u32 root, fat, lba, io_lba = 0;
    fail(r, RB_CONFIG_MISSING, 0, 0);
    c.read = read; c.opaque = opaque; c.at = 0;
    rb_scan_partitions(&scan, captured_read, &c, low, high, disk_id);
    if (scan.status != 0) { fail(r, RB_CONFIG_SCAN, scan.status, scan.error_lba); return; }
    if (c.sector[432] != 'R' || c.sector[433] != 'B' || c.sector[434] != 'M'
            || c.sector[435] != '1' || dword(c.sector + 436) != admin_lba) {
        fail(r, RB_CONFIG_ADMIN, 0, 0); return;
    }
    for (i = 4; i < scan.count; ++i) {
        if (scan.entries[i].start == admin_lba && (scan.entries[i].type == 0x16
                || scan.entries[i].type == 0x1E)) { admin = &scan.entries[i]; }
    }
    if (admin == (rb_partition *)0) { fail(r, RB_CONFIG_ADMIN, 0, admin_lba); return; }
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
            for (copy = 0; copy < 2; ++copy) {
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
    if (clusters[0] != 0 && clusters[0] == clusters[1]) {
        fail(r, RB_CONFIG_DIRECTORY, 2, root); return;
    }
    for (copy = 0; copy < 2; ++copy) {
        if (clusters[copy] == 0) { continue; }
        for (i = 0; i < 2; ++i) {
            lba = fat + i * volume.fat_sectors + clusters[copy] / 256;
            if (read(lba, sector, opaque)) { fail(r, RB_CONFIG_IO, 0, lba); return; }
            value = word(sector + (clusters[copy] % 256) * 2);
            if (value < 0xFFF8U || (i && value != previous)) { fail(r, RB_CONFIG_FAT, copy, lba); return; }
            previous = value;
        }
        lba = volume.data_lba + ((rb_u32)clusters[copy] - 2) * spc;
        if (read(lba, records[copy], opaque)) { io_mask |= 1U << copy; io_lba = lba; }
        else { mask |= 1U << copy; }
    }
    rb_config_select(r, records[0], records[1], mask, &scan, admin);
    if (r->status && r->status != RB_CONFIG_CONFLICT && r->status != RB_CONFIG_MISSING) {
        copy = r->copies[0] == r->status ? 0 : 1;
        r->error_lba = volume.data_lba + ((rb_u32)clusters[copy] - 2) * spc;
    }
    if (io_mask) {
        for (i = 0; i < 2; ++i) { if (io_mask & (1U << i)) { r->copies[i] = RB_CONFIG_IO; } }
        r->error_lba = io_lba;
        if (r->source == RB_CONFIG_NONE) { r->status = RB_CONFIG_IO; }
    }
}
