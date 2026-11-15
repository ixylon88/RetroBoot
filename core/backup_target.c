#include "backup_target.h"
#include "admin_audit.h"
#include "state.h"

static struct {
    rb_admin_audit audit;
    rb_config_result config;
    rb_state_result state;
    rb_u8 mbr[512], a[512], b[512];
    rb_sector_reader read;
    void *opaque;
    const rb_rescue_device *device;
    rb_u32 digest[2], error_lba;
    rb_u16 reads, have_mbr, changed;
} work;

static void clear(void *p, rb_u16 n)
{
    rb_u8 *bytes = (rb_u8 *)p;
    while (n) { bytes[--n] = 0; }
}
static rb_u16 same(const rb_u8 *a, const rb_u8 *b, rb_u16 n)
{
    while (n) { --n; if (a[n] != b[n]) { return 0; } } return 1;
}
static rb_u32 dword(const rb_u8 *p)
{
    return (rb_u32)p[0] | ((rb_u32)p[1] << 8) | ((rb_u32)p[2] << 16) | ((rb_u32)p[3] << 24);
}
static rb_u16 nonzero(const rb_u8 *p)
{
    rb_u16 i;
    for (i = 0; i < 16; ++i) { if (p[i]) { return 1; } } return 0;
}
static void fail(rb_backup_target *r, rb_u16 code, rb_u16 detail, rb_u32 lba)
{
    clear(r, sizeof(*r)); r->status = code; r->detail = detail; r->error_lba = lba;
}
/* Include order, address and every byte in separate sector-half chains.
   A CRC over a complete CRC-suffixed record has a constant residue, even
   after a correctly resealed change. Keeping the halves separate avoids
   that blind spot. CRCs still do not authenticate a source. */
static rb_u16 __cdecl observed_read(rb_u32 lba, rb_u8 *out, void *opaque)
{
    rb_u32 tuple[3];
    rb_u16 i;
    (void)opaque;
    work.error_lba = lba;
    if ((!work.device->capacity_high && lba >= work.device->capacity_low)
            || work.read(lba, out, work.opaque)) { return 1; }
    if (!lba) {
        if (work.have_mbr && !same(work.mbr, out, 512)) { work.changed = 1; return 1; }
        if (!work.have_mbr) { for (i = 0; i < 512; ++i) { work.mbr[i] = out[i]; } }
        work.have_mbr = 1;
    }
    for (i = 0; i < 2; ++i) {
        tuple[0] = work.digest[i]; tuple[1] = lba; tuple[2] = rb_crc32(out + i * 256, 256);
        work.digest[i] = rb_crc32((const rb_u8 *)tuple, sizeof(tuple));
    }
    ++work.reads;
    return 0;
}
static void io_failure(rb_backup_target *r, rb_u16 detail)
{
    fail(r, work.changed ? RB_BTARGET_CHANGED : RB_BTARGET_IO, detail, work.error_lba);
}

static void acquire(rb_backup_target *r)
{
    const rb_partition *admin = (const rb_partition *)0;
    rb_u16 i, code;
    rb_u32 lba;
    work.digest[0] = work.digest[1] = 0; work.reads = work.have_mbr = work.changed = 0;
    fail(r, RB_BTARGET_OK, 0, 0);
    if (observed_read(0, work.a, (void *)0)) { io_failure(r, 0); return; }
    if (work.mbr[510] != 0x55 || work.mbr[511] != 0xAA
            || !same(work.mbr + 432, (const rb_u8 *)"RBM1", 4)
            || !dword(work.mbr + 440) || !dword(work.mbr + 436)) {
        fail(r, RB_BTARGET_IDENTITY, 1, 0); return;
    }
    /* Both arguments are independently observed above, not supplied by backup. */
    code = rb_audit_admin(&work.audit, observed_read, (void *)0,
        work.device->capacity_low, work.device->capacity_high,
        dword(work.mbr + 440), dword(work.mbr + 436));
    if (code) {
        fail(r, work.changed ? RB_BTARGET_CHANGED : RB_BTARGET_ALLOCATION,
            code, work.audit.error_lba); return;
    }
    for (i = 4; i < work.audit.scan.count; ++i) {
        if (work.audit.scan.entries[i].start == dword(work.mbr + 436)) { admin = &work.audit.scan.entries[i]; }
    }
    if (!admin) { fail(r, RB_BTARGET_IDENTITY, 1, 0); return; }
    for (i = 0; i < 4; ++i) {
        lba = work.audit.files[i + 2].first_lba;
        if (observed_read(lba, i & 1 ? work.b : work.a, (void *)0)) { io_failure(r, i + 5); return; }
        if (i == 1) {
            rb_config_select(&work.config, work.a, work.b, 3, &work.audit.scan, admin);
            code = work.config.status ? work.config.status : work.config.copies[0]
                ? work.config.copies[0] : work.config.copies[1];
            if (code) {
                fail(r, RB_BTARGET_CONFIG, code, work.config.copies[0] ? work.audit.files[2].first_lba
                    : work.config.copies[1] ? work.audit.files[3].first_lba : 0); return;
            }
            if (work.a[8] != 2 || work.b[8] != 2 || !same(work.a + 48, work.b + 48, 16)) {
                fail(r, RB_BTARGET_IDENTITY, 2, lba); return;
            }
        } else if (i == 3) {
            rb_state_select(&work.state, work.a, work.b, 3, &work.audit.scan, admin);
            code = work.state.status ? work.state.status : work.state.copies[0]
                ? work.state.copies[0] : work.state.copies[1];
            if (code) {
                fail(r, RB_BTARGET_STATE, code, work.state.copies[0] ? work.audit.files[4].first_lba
                    : work.state.copies[1] ? work.audit.files[5].first_lba : 0); return;
            }
            if (!same(work.config.config.media_id, work.a + 48, 16)
                    || !same(work.config.config.media_id, work.b + 48, 16)) {
                fail(r, RB_BTARGET_IDENTITY, 3, lba); return;
            }
        }
    }
    if (observed_read(0, work.a, (void *)0)) { io_failure(r, 0); return; }
    r->disk_id = dword(work.mbr + 440); r->layout_crc = rb_layout_crc(&work.audit.scan);
    r->admin_start = admin->start; r->admin_sectors = admin->sectors;
    for (i = 0; i < 16; ++i) { r->media_id[i] = work.config.config.media_id[i]; }
    r->config_generation = work.config.config.generation; r->state_generation = work.state.state.generation;
}

static rb_u16 geometry(rb_u16 route, rb_u16 heads, rb_u16 spt, rb_u32 low, rb_u32 high)
{
    if (!low && !high) { return 0; }
    if (route == 1 && !heads && !spt) { return 1; }
    if ((route != 1 && route != 2) || !heads || heads > 256 || !spt || spt > 63) { return 0; }
    return route == 1 || (!high && low <= (rb_u32)heads * spt * 1024UL);
}

void rb_backup_observe_target(rb_backup_target *r, rb_backup_sources *sources,
    const rb_rescue_device *d, rb_sector_reader read, void *opaque)
{
    rb_u32 digest[2];
    rb_u16 reads, i;
    clear(&work, sizeof(work)); fail(r, RB_BTARGET_PARAMS, 0, 0);
    if (sources) { clear(sources, sizeof(*sources)); }
    if (!d || !read) { return; }
    if (d->drive != 0x80 || d->mode > 1
            || !geometry(d->mode ? 1 : 2, d->heads, d->sectors_per_track, d->capacity_low, d->capacity_high)) {
        r->detail = 2; return;
    }
    work.read = read; work.opaque = opaque; work.device = d;
    acquire(r);
    if (!r->status) {
        digest[0] = work.digest[0]; digest[1] = work.digest[1]; reads = work.reads;
        acquire(r);
        if (!r->status && (work.digest[0] != digest[0] || work.digest[1] != digest[1] || work.reads != reads)) {
            fail(r, RB_BTARGET_CHANGED, 0, 0);
        }
    }
    if (!r->status && sources) {
        sources->scan = work.audit.scan;
        for (i = 0; i < 4; ++i) { sources->record_lba[i] = work.audit.files[i + 2].first_lba; }
        for (i = 0; i < work.state.state.count; ++i) {
            if (work.state.state.entries[i].phase == RB_INSTALL_READY) {
                sources->ready[sources->ready_count].start = work.state.state.entries[i].start;
                sources->ready[sources->ready_count].vbr_crc = work.state.state.entries[i].vbr_crc;
                sources->ready[sources->ready_count++].index = i;
            }
        }
    }
    clear(&work, sizeof(work));
}

void rb_backup_match_target(rb_backup_target *r, const rb_backup *b,
    const rb_rescue_device *d, rb_sector_reader read, void *opaque)
{
    rb_u16 route;
    clear(&work, sizeof(work)); fail(r, RB_BTARGET_PARAMS, 0, 0);
    if (!b || !d || !read) { return; }
    route = d->mode ? 1 : 2;
    if (!b->disk_id || !nonzero(b->media_id) || !b->admin_start || !b->admin_sectors
            || b->admin_start + b->admin_sectors <= b->admin_start
            || (!b->capacity_high && b->admin_start + b->admin_sectors > b->capacity_low)
            || !geometry(b->route, b->heads, b->sectors_per_track, b->capacity_low, b->capacity_high)) {
        r->detail = 1; return;
    }
    if (d->drive != 0x80 || d->mode > 1
            || !geometry(route, d->heads, d->sectors_per_track, d->capacity_low, d->capacity_high)) {
        r->detail = 2; return;
    }
    if (b->capacity_low != d->capacity_low || b->capacity_high != d->capacity_high) {
        fail(r, RB_BTARGET_CAPACITY, 0, 0); return;
    }
    if (b->route != route || b->heads != d->heads || b->sectors_per_track != d->sectors_per_track) {
        fail(r, RB_BTARGET_GEOMETRY, 0, 0); return;
    }
    rb_backup_observe_target(r, (rb_backup_sources *)0, d, read, opaque);
    if (!r->status) {
        if (r->disk_id != b->disk_id || !same(r->media_id, b->media_id, 16)) {
            fail(r, RB_BTARGET_IDENTITY, 4, 0);
        } else if (r->layout_crc != b->layout_crc || r->admin_start != b->admin_start || r->admin_sectors != b->admin_sectors) {
            fail(r, RB_BTARGET_LAYOUT, 0, 0);
        }
    }
}
