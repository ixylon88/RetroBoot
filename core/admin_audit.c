#include "admin_audit.h"

const char * const rb_audit_names[RB_AUDIT_FILES] = {
    "RBBOOT.SYS", "RBSTG2.BIN", "RBCFG.A", "RBCFG.B", "RBSTATE.A", "RBSTATE.B"
};
static const char short_names[RB_AUDIT_FILES][12] = {
    "RBBOOT  SYS", "RBSTG2  BIN", "RBCFG   A  ", "RBCFG   B  ", "RBSTATE A  ", "RBSTATE B  "
};

typedef struct { rb_u16 cluster, next, file; } allocation;
static struct {
    rb_partition_scan scan;
    rb_volume_probe volume;
    rb_u8 a[512], b[512];
    allocation nodes[RB_AUDIT_NODES];
    rb_sector_reader read;
    void *opaque;
    rb_u32 capture_lba, fat, root, bootstrap_lba;
    rb_u16 bootstrap_sectors, node_count, cached, cache_valid;
} work;

static rb_u16 word(const rb_u8 *p) { return p[0] | ((rb_u16)p[1] << 8); }
static rb_u32 dword(const rb_u8 *p) { return (rb_u32)word(p) | ((rb_u32)word(p + 2) << 16); }

static void clear_work(void)
{
    rb_u16 i;
    rb_u8 *p = (rb_u8 *)&work;
    for (i = 0; i < sizeof(work); ++i) { p[i] = 0; }
}

static rb_u16 fail(rb_admin_audit *r, rb_u16 status, rb_u16 detail,
                   rb_u32 lba, rb_u16 file, rb_u16 cluster)
{
    rb_u16 i;
    rb_u8 *p = (rb_u8 *)r;
    for (i = 0; i < sizeof(*r); ++i) { p[i] = 0; }
    r->status = status; r->detail = detail; r->error_lba = lba;
    r->error_file = file; r->error_cluster = cluster;
    clear_work();
    return status;
}

static rb_u16 __cdecl captured_read(rb_u32 lba, rb_u8 *sector, void *opaque)
{
    rb_u16 i, status;
    (void)opaque;
    status = work.read(lba, sector, work.opaque);
    if (!status && lba == work.capture_lba) {
        for (i = 0; i < 512; ++i) { work.a[i] = sector[i]; }
    }
    return status;
}

/* Compare whole FAT sectors, including padding. The final sweep bypasses this
 * small cache and checks every captured chain successor against the new read. */
static rb_u16 fat_pair(rb_admin_audit *r, rb_u16 index, rb_u16 file, rb_u16 cluster)
{
    rb_u16 i;
    rb_u32 lba = work.fat + index;
    if (work.read(lba, work.a, work.opaque)) { return fail(r, RB_AUDIT_IO, 0, lba, file, cluster); }
    lba += work.volume.fat_sectors;
    if (work.read(lba, work.b, work.opaque)) { return fail(r, RB_AUDIT_IO, 0, lba, file, cluster); }
    for (i = 0; i < 512; ++i) {
        if (work.a[i] != work.b[i]) { return fail(r, RB_AUDIT_COPIES, 0, lba, file, cluster); }
    }
    if (!index && (word(work.a) != 0xFFF8U || word(work.a + 2) != 0xFFFFU)) {
        return fail(r, RB_AUDIT_HEADER, 0, work.fat, file, cluster);
    }
    work.cached = index; work.cache_valid = 1;
    return 0;
}

rb_u16 rb_audit_admin(rb_admin_audit *r, rb_sector_reader read, void *opaque,
                      rb_u32 low, rb_u32 high, rb_u32 disk_id, rb_u32 admin_lba)
{
    rb_partition *admin = (rb_partition *)0;
    rb_audit_file *file;
    allocation saved;
    rb_u8 *entry;
    rb_u16 i, j, k, n, found, match, ended = 0, sum = 0, spc, cluster, next, owner, free = 0;
    rb_u32 lba, maximum;

    fail(r, RB_AUDIT_OK, 0, 0, 0, 0);
    work.read = read; work.opaque = opaque; work.capture_lba = 0;
    work.node_count = work.cache_valid = 0;
    rb_scan_partitions(&work.scan, captured_read, (void *)0, low, high, disk_id);
    if (work.scan.status) {
        return fail(r, RB_AUDIT_SCAN, work.scan.status, work.scan.error_lba, 0, 0);
    }
    if (work.a[432] != 'R' || work.a[433] != 'B' || work.a[434] != 'M'
            || work.a[435] != '1' || dword(work.a + 436) != admin_lba) {
        return fail(r, RB_AUDIT_ADMIN, 0, 0, 0, 0);
    }
    for (i = 4; i < work.scan.count; ++i) {
        if (work.scan.entries[i].start == admin_lba && (work.scan.entries[i].type == 0x16
                || work.scan.entries[i].type == 0x1E)) { admin = &work.scan.entries[i]; }
    }
    if (!admin) { return fail(r, RB_AUDIT_ADMIN, 0, admin_lba, 0, 0); }
    work.capture_lba = admin_lba;
    rb_probe_volume(&work.volume, admin, captured_read, (void *)0, low, high);
    if (work.volume.status) { return fail(r, RB_AUDIT_ADMIN, work.volume.status, admin_lba, 0, 0); }
    for (i = 0; i < 512; i += 2) { sum += word(work.a + i); }
    if (work.volume.fat_bits != 16 || work.volume.fats != 2 || word(work.a + 14) != 1
            || word(work.a + 17) != 512 || work.a[21] != 0xF8 || sum
            || work.volume.total_sectors != admin->sectors || work.volume.fat_sectors > 256UL
            || work.volume.clusters > 0xFFEEUL || work.a[62] != 'R' || work.a[63] != 'B'
            || work.a[64] != 'V' || work.a[65] != '1') {
        return fail(r, RB_AUDIT_ADMIN, 0, admin_lba, 0, 0);
    }
    work.bootstrap_lba = dword(work.a + 66); work.bootstrap_sectors = word(work.a + 70);
    work.fat = admin_lba + 1; work.root = work.fat + 2 * work.volume.fat_sectors;
    spc = work.volume.cluster_bytes / 512;

    for (i = 0; i < 32 && !ended; ++i) {
        lba = work.root + i;
        if (read(lba, work.a, opaque)) { return fail(r, RB_AUDIT_IO, 0, lba, 0, 0); }
        for (j = 0; j < 16; ++j) {
            entry = work.a + j * 32;
            if (!entry[0]) { ended = 1; break; }
            if (entry[0] == 0xE5) { continue; }
            /* A volume label has no data chain. Directories/LFN are outside
             * this deliberately closed six-file format, not silently skipped. */
            if (entry[11] == 8 && !word(entry + 20) && !word(entry + 26) && !dword(entry + 28)) { continue; }
            found = RB_AUDIT_FILES;
            for (k = 0; k < RB_AUDIT_FILES; ++k) {
                match = 1;
                for (n = 0; n < 11; ++n) { if (entry[n] != (rb_u8)short_names[k][n]) { match = 0; } }
                if (match) { found = k; break; }
            }
            if (found == RB_AUDIT_FILES) { return fail(r, RB_AUDIT_ROOT, 1, lba, 0, word(entry + 26)); }
            file = &r->files[found];
            if (file->first_cluster) { return fail(r, RB_AUDIT_ROOT, 2, lba, found + 1, word(entry + 26)); }
            if ((entry[11] & 0xD8U) || word(entry + 20)) {
                return fail(r, RB_AUDIT_ROOT, 4, lba, found + 1, word(entry + 26));
            }
            file->bytes = dword(entry + 28); cluster = word(entry + 26);
            maximum = found == 0 ? 8192UL : found == 1 ? 49152UL : 512UL;
            if (!file->bytes || file->bytes > maximum || (found == 0 && file->bytes % 512)
                    || (found >= 2 && file->bytes != 512)) {
                return fail(r, RB_AUDIT_ROOT, 5, lba, found + 1, cluster);
            }
            if (cluster < 2 || (rb_u32)cluster > work.volume.clusters + 1) {
                return fail(r, RB_AUDIT_ROOT, 6, lba, found + 1, cluster);
            }
            file->first_cluster = cluster;
            file->clusters = (rb_u16)((file->bytes + work.volume.cluster_bytes - 1) / work.volume.cluster_bytes);
            file->first_lba = work.volume.data_lba + ((rb_u32)cluster - 2) * spc;
        }
    }
    for (i = 0; i < RB_AUDIT_FILES; ++i) {
        if (!r->files[i].first_cluster) { return fail(r, RB_AUDIT_ROOT, 3, work.root, i + 1, 0); }
    }
    if (r->files[0].first_lba != work.bootstrap_lba
            || r->files[0].bytes / 512 != work.bootstrap_sectors) {
        return fail(r, RB_AUDIT_BOOTSTRAP, 0, admin_lba, 1, r->files[0].first_cluster);
    }

    for (i = 0; i < RB_AUDIT_FILES; ++i) {
        file = &r->files[i]; cluster = file->first_cluster;
        for (j = 0; j < file->clusters; ++j) {
            lba = work.fat + cluster / 256;
            if (cluster < 2 || (rb_u32)cluster > work.volume.clusters + 1) {
                return fail(r, RB_AUDIT_CHAIN, cluster, lba, i + 1, cluster);
            }
            for (k = 0; k < work.node_count; ++k) {
                if (work.nodes[k].cluster == cluster) {
                    return fail(r, work.nodes[k].file == i + 1 ? RB_AUDIT_CHAIN : RB_AUDIT_SHARED,
                                work.nodes[k].file, lba, i + 1, cluster);
                }
            }
            if (work.node_count == RB_AUDIT_NODES) { return fail(r, RB_AUDIT_CHAIN, 0, lba, i + 1, cluster); }
            if (!work.cache_valid || work.cached != cluster / 256) {
                if (fat_pair(r, cluster / 256, i + 1, cluster)) { return r->status; }
            }
            next = word(work.a + (cluster % 256) * 2);
            if (j + 1 == file->clusters ? next < 0xFFF8U
                    : next < 2 || (rb_u32)next > work.volume.clusters + 1) {
                return fail(r, RB_AUDIT_CHAIN, next, lba, i + 1, cluster);
            }
            if (!i && j + 1 < file->clusters && next != cluster + 1) {
                return fail(r, RB_AUDIT_BOOTSTRAP, next, lba, 1, cluster);
            }
            work.nodes[work.node_count].cluster = cluster;
            work.nodes[work.node_count].next = next;
            work.nodes[work.node_count++].file = i + 1;
            cluster = next;
        }
    }

    /* The bounded file sizes need at most 116 ownership entries, not a 64 KiB
     * FAT in near memory. Sorting permits one linear sweep of both full FATs. */
    for (i = 1; i < work.node_count; ++i) {
        saved = work.nodes[i]; j = i;
        while (j && work.nodes[j - 1].cluster > saved.cluster) { work.nodes[j] = work.nodes[j - 1]; --j; }
        work.nodes[j] = saved;
    }
    owner = 0;
    for (i = 0; (rb_u32)i < work.volume.fat_sectors; ++i) {
        if (fat_pair(r, i, 0, 0)) { return r->status; }
        for (j = 0; j < 256; ++j) {
            cluster = i * 256U + j;
            if (cluster < 2 || (rb_u32)cluster > work.volume.clusters + 1) { continue; }
            next = word(work.a + j * 2);
            if (owner < work.node_count && work.nodes[owner].cluster == cluster) {
                if (next != work.nodes[owner].next) {
                    return fail(r, RB_AUDIT_CHANGED, next, work.fat + i, work.nodes[owner].file, cluster);
                }
                ++owner;
            } else if (next) { return fail(r, RB_AUDIT_ORPHAN, next, work.fat + i, 0, cluster); }
            else { ++free; }
        }
    }
    r->total_clusters = (rb_u16)work.volume.clusters;
    r->used_clusters = work.node_count; r->free_clusters = free;
    clear_work();
    return RB_AUDIT_OK;
}
