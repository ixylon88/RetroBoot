#include "fingerprint.h"
#include "backup_plan.h"
#include "config.h"
#include "volume.h"
#include "backup_boot.h"
#include "fat_boot.h"

static struct {
    rb_backup_sources sources;
    rb_rescue_device device;
    rb_sector_reader read;
    void *opaque;
    rb_u8 mbr[512], header[512];
    rb_u32 digest[2], reads, error_lba;
    rb_u16 have_mbr, changed;
} work;

static void clear(void *p, rb_u16 n)
{
    rb_u8 *bytes = (rb_u8 *)p;
    while (n) { bytes[--n] = 0; }
}
static rb_u16 word(const rb_u8 *p) { return p[0] | ((rb_u16)p[1] << 8); }
static rb_u16 equal(const rb_u8 *a, const rb_u8 *b)
{
    rb_u16 i;
    for (i = 0; i < 512; ++i) { if (a[i] != b[i]) { return 0; } }
    return 1;
}
static void fail(rb_backup_plan *r, rb_u16 code, rb_u16 detail,
                 rb_u16 nested, rb_u16 index, rb_u32 lba)
{
    clear(r, sizeof(*r)); r->status = code; r->detail = detail;
    r->nested = nested; r->index = index; r->error_lba = lba;
}
/* Track every observed byte, physical address and read order. */
static rb_u16 __cdecl tracked_read(rb_u32 lba, rb_u8 *out, void *opaque)
{
    rb_u16 i;
    (void)opaque; work.error_lba = lba;
    if ((!work.device.capacity_high && lba >= work.device.capacity_low)
            || work.read(lba, out, work.opaque)) { return 1; }
    if (!lba) {
        for (i = 0; i < 512; ++i) {
            if (work.have_mbr && work.mbr[i] != out[i]) { work.changed = 1; return 1; }
            work.mbr[i] = out[i];
        }
        work.have_mbr = 1;
    }
    rb_fingerprint_sector(work.digest, lba, out);
    ++work.reads; return 0;
}
static rb_u16 __cdecl header_read(rb_u32 lba, rb_u8 *out, void *opaque)
{
    rb_u16 i;
    if (tracked_read(lba, out, opaque)) { return 1; }
    for (i = 0; i < 512; ++i) { work.header[i] = out[i]; }
    return 0;
}
static rb_u16 append(rb_backup_plan *r, rb_u16 kind, rb_u16 index,
    rb_u32 lba, rb_u32 sectors, rb_u32 owner, rb_u32 owner_sectors)
{
    rb_u16 i;
    rb_capture_extent *e;
    if (!sectors || lba > 0xFFFFFFFFUL - sectors
            || (!work.device.capacity_high && lba + sectors > work.device.capacity_low)
            || (owner && (owner > 0xFFFFFFFFUL - owner_sectors || lba < owner
                || lba + sectors > owner + owner_sectors))) {
        fail(r, RB_CAPTURE_RANGE, kind, 0, index, lba); return 1;
    }
    for (i = 0; i < r->count; ++i) {
        e = &r->entries[i];
        if (lba < e->lba + e->sectors && e->lba < lba + sectors) {
            fail(r, RB_CAPTURE_RANGE, kind, 1, index, lba); return 1;
        }
    }
    if (r->count == RB_CAPTURE_MAX || sectors > RB_BACKUP_SECTORS - 6 - r->live_sectors) {
        fail(r, RB_CAPTURE_LIMIT, kind, 0, index, lba); return 1;
    }
    e = &r->entries[r->count++]; e->kind = kind; e->index = index;
    e->lba = lba; e->sectors = sectors; e->owner_start = owner; e->owner_sectors = owner_sectors;
    r->live_sectors += sectors; return 0;
}
/* The complete plan and its size bound must exist before any full-area read.
   Buffers are bounded stack scratch; no reserved area is retained in memory. */
static rb_u16 check_boot(rb_backup_plan *r, const rb_partition *p,
                        rb_u16 index, rb_u16 reserved)
{
    rb_u8 sector[512], continuation[512];
    rb_volume_probe volume;
    rb_u16 code, backup, offset, i;
    rb_u32 lba, crc;
    code = rb_probe_volume(&volume, p, header_read, (void *)0,
        work.device.capacity_low, work.device.capacity_high);
    if (code) {
        fail(r, code == RB_VOLUME_IO ? RB_CAPTURE_IO : RB_CAPTURE_VOLUME,
            code, 0, index, p->start); return 1;
    }
    if (word(work.header + 14) != reserved) {
        fail(r, RB_CAPTURE_CHANGED, 0, 0, index, p->start); return 1;
    }
    backup = volume.fat_bits == 32 ? word(work.header + 50) : 0;
    if (volume.fat_bits == 32 && (word(work.header + 48) != 1 || reserved < 3
            || (backup && (backup < 3 || (rb_u32)backup + 3 > reserved)))) {
        fail(r, RB_CAPTURE_FAT32_LAYOUT, 0, 0, index, p->start); return 1;
    }
    for (offset = 1; offset < reserved; ++offset) {
        lba = p->start + offset;
        if (tracked_read(lba, sector, (void *)0)) {
            fail(r, RB_CAPTURE_IO, RB_VOLUME_IO, 0, index, lba); return 1;
        }
        if (volume.fat_bits != 32) { continue; }
        if (offset == 1 || (backup && offset == backup + 1)) {
            code = rb_fat32_fsinfo(sector, volume.clusters);
            if (code) {
                fail(r, RB_CAPTURE_BOOT, RB_BBOOT_FSINFO, code, index, lba); return 1;
            }
        } else if (offset == 2) {
            if (word(sector + 510) != 0xAA55) {
                fail(r, RB_CAPTURE_BOOT, RB_BBOOT_COPY, 3, index, lba); return 1;
            }
            for (i = 0; i < 512; ++i) { continuation[i] = sector[i]; }
        } else if (backup && (offset == backup || offset == backup + 2)) {
            if (!equal(sector, offset == backup ? work.header : continuation)) {
                fail(r, RB_CAPTURE_BOOT, RB_BBOOT_COPY, offset == backup ? 1 : 2, index, lba); return 1;
            }
        }
    }
    crc = rb_crc32(work.header, 512);
    for (i = 0; i < work.sources.ready_count; ++i) {
        if (work.sources.ready[i].start == p->start && work.sources.ready[i].vbr_crc != crc) {
            fail(r, RB_CAPTURE_BOOT, RB_BBOOT_READY, work.sources.ready[i].index, index, p->start);
            return 1;
        }
    }
    return 0;
}
static void acquire(rb_backup_plan *r)
{
    rb_volume_probe volume;
    const rb_partition *p;
    rb_u16 i, code, reserved, backup, extent;
    fail(r, RB_CAPTURE_OK, 0, 0, 0, 0);
    work.digest[0] = work.digest[1] = work.reads = 0;
    work.have_mbr = work.changed = 0;
    rb_backup_observe_target(&r->observed, &work.sources, &work.device, tracked_read, (void *)0);
    if (r->observed.status) {
        fail(r, work.changed ? RB_CAPTURE_CHANGED : RB_CAPTURE_TARGET,
            r->observed.status, r->observed.detail, 0, r->observed.error_lba); return;
    }
    if (append(r, RB_CAPTURE_CURRENT_MBR, 0, 0, 1, 0, 0)) { return; }
    for (i = 0; i < work.sources.scan.ebr_count; ++i) {
        if (append(r, RB_BACKUP_EBR, i, work.sources.scan.ebr_lba[i], 1, 0, 0)) { return; }
    }
    for (i = 0; i < work.sources.scan.count; ++i) {
        p = &work.sources.scan.entries[i];
        if (!p->type || p->type == 5 || p->type == 15) { continue; }
        code = rb_probe_volume(&volume, p, header_read, (void *)0,
            work.device.capacity_low, work.device.capacity_high);
        if (code) {
            fail(r, code == RB_VOLUME_IO ? RB_CAPTURE_IO : RB_CAPTURE_VOLUME,
                code, 0, i, p->start); return;
        }
        reserved = word(work.header + 14);
        if (volume.fat_bits == 32) {
            backup = word(work.header + 50);
            if (word(work.header + 48) != 1 || reserved < 3
                    || (backup && (backup < 3 || (rb_u32)backup + 3 > reserved))) {
                fail(r, RB_CAPTURE_FAT32_LAYOUT, 0, 0, i, p->start); return;
            }
        }
        if (append(r, RB_BACKUP_BOOT, r->volumes, p->start, reserved, p->start, p->sectors)) { return; }
        ++r->volumes;
    }
    for (i = 0; i < 4; ++i) {
        if (append(r, RB_BACKUP_CONFIG_A + i, 0, work.sources.record_lba[i], 1,
                r->observed.admin_start, r->observed.admin_sectors)) { return; }
    }
    extent = 1 + work.sources.scan.ebr_count;
    for (i = 0; i < work.sources.scan.count; ++i) {
        p = &work.sources.scan.entries[i];
        if (!p->type || p->type == 5 || p->type == 15) { continue; }
        if (check_boot(r, p, i, (rb_u16)r->entries[extent++].sectors)) { return; }
    }
    if (tracked_read(0, work.header, (void *)0)) {
        fail(r, work.changed ? RB_CAPTURE_CHANGED : RB_CAPTURE_IO, 0, 0, 0, 0); return;
    }
    r->device = work.device; r->estimated_container_sectors = r->live_sectors + 6;
}

void rb_backup_plan_capture(rb_backup_plan *r, const rb_rescue_device *d,
    rb_sector_reader read, void *opaque)
{
    rb_u32 digest[2], reads;
    clear(&work, sizeof(work)); fail(r, RB_CAPTURE_PARAMS, 0, 0, 0, 0);
    if (!d || !read) { return; }
    work.device = *d; work.read = read; work.opaque = opaque;
    acquire(r);
    if (!r->status) {
        digest[0] = work.digest[0]; digest[1] = work.digest[1]; reads = work.reads;
        acquire(r);
        if (!r->status && (work.digest[0] != digest[0] || work.digest[1] != digest[1] || work.reads != reads)) {
            fail(r, RB_CAPTURE_CHANGED, 0, 0, 0, 0);
        }
    }
    clear(&work, sizeof(work));
}
