#include "backup_live.h"
#include "backup_format.h"
#include "fingerprint.h"

static struct {
    rb_backup_payloads captured;
    rb_rescue_device device;
    rb_sector_reader read;
    rb_backup_source mbr_source;
    void *disk_opaque, *mbr_opaque;
    rb_u32 digest[2], reads;
} work;

static void clear(void *p, rb_u16 size)
{
    rb_u8 *bytes = (rb_u8 *)p;
    while (size) { bytes[--size] = 0; }
}
static rb_u16 same(const rb_u8 *a, const rb_u8 *b, rb_u16 size)
{
    while (size) { --size; if (a[size] != b[size]) { return 0; } }
    return 1;
}
static rb_u16 fail(rb_backup_live_result *r, rb_u16 code, rb_u16 detail, rb_u32 lba)
{
    r->status = code; r->detail = detail; r->error_lba = lba;
    r->stream.sectors = 0; return code;
}
static rb_u16 __cdecl audited_read(rb_u32 lba, rb_u8 *out, void *opaque)
{
    (void)opaque;
    if (work.read(lba, out, work.disk_opaque)) { return 1; }
    rb_fingerprint_sector(work.digest, lba, out); ++work.reads;
    return 0;
}
static rb_u16 capture(rb_backup_live_result *r)
{
    const rb_backup_plan *p = &work.captured.plan;
    work.digest[0] = work.digest[1] = work.reads = 0;
    rb_backup_payload_capture(&work.captured, &work.device, audited_read, (void *)0);
    if (!p->status) { return 0; }
    r->capture_status = p->status; r->capture_detail = p->detail;
    r->capture_nested = p->nested; r->capture_index = p->index;
    return fail(r, RB_LIVE_CAPTURE, 0, p->error_lba);
}
static rb_u16 binding(rb_backup_live_result *r, const rb_backup *b)
{
    const rb_backup_plan *p = &work.captured.plan;
    const rb_backup_target *t = &p->observed;
    const rb_backup_extent *e;
    const rb_capture_extent *live;
    rb_u16 i;
    if (b->capacity_low != p->device.capacity_low || b->capacity_high != p->device.capacity_high) {
        return fail(r, RB_LIVE_IDENTITY, 1, 0);
    }
    if (b->route != (p->device.mode ? 1 : 2) || b->heads != p->device.heads
            || b->sectors_per_track != p->device.sectors_per_track) {
        return fail(r, RB_LIVE_IDENTITY, 2, 0);
    }
    if (b->disk_id != t->disk_id || !same(b->media_id, t->media_id, 16)) {
        return fail(r, RB_LIVE_IDENTITY, 3, 0);
    }
    if (b->layout_crc != t->layout_crc || b->admin_start != t->admin_start
            || b->admin_sectors != t->admin_sectors) {
        return fail(r, RB_LIVE_IDENTITY, 4, 0);
    }
    /* The current-MBR observation is deliberately omitted. Both on-disk MBR
       roles are supplied separately, even if their bytes happen to agree. */
    if (b->count != p->count + 1) { return fail(r, RB_LIVE_EXTENT, 0, 0); }
    for (i = 1; i < p->count; ++i) {
        e = &b->entries[i + 1]; live = &p->entries[i];
        if (e->kind != live->kind || e->index != live->index || e->lba != live->lba
                || e->sectors != live->sectors || e->owner_start != live->owner_start
                || e->owner_sectors != live->owner_sectors || e->crc != work.captured.crc[i]) {
            return fail(r, RB_LIVE_EXTENT, i + 1, live->lba);
        }
    }
    return 0;
}
static rb_u16 __cdecl source(rb_u16 kind, rb_u16 index, rb_u32 offset,
    rb_u8 *out, void *opaque)
{
    const rb_capture_extent *e;
    rb_u16 i;
    (void)opaque;
    if (kind == RB_BACKUP_ORIGINAL || kind == RB_BACKUP_APPROVED) {
        if (index || offset) { return 1; }
        return work.mbr_source(kind, index, offset, out, work.mbr_opaque);
    }
    for (i = 1; i < work.captured.plan.count; ++i) {
        e = &work.captured.plan.entries[i];
        if (kind != e->kind || index != e->index) { continue; }
        if (offset >= e->sectors || e->lba > 0xFFFFFFFFUL - offset
                || (!work.device.capacity_high && e->lba + offset >= work.device.capacity_low)) {
            return 1;
        }
        return work.read(e->lba + offset, out, work.disk_opaque);
    }
    return 1;
}

rb_u16 rb_backup_live_stream(rb_backup_live_result *r,
    const rb_backup *b, rb_u32 size, const rb_rescue_device *d,
    rb_sector_reader read, void *disk_opaque,
    rb_backup_source mbr_source, void *mbr_opaque,
    rb_backup_sink sink, void *sink_opaque)
{
    rb_u32 first[2], reads;
    rb_u16 code;
    if (!r) { return RB_LIVE_PARAMS; }
    clear(&work, sizeof(work)); clear(r, sizeof(*r));
    fail(r, RB_LIVE_PARAMS, 0, 0);
    if (!b || !d || !read || !mbr_source || !sink) { goto done; }
    code = rb_backup_identity(b, size);
    if (!code) { code = rb_backup_entries(b, size); }
    if (code) { fail(r, RB_LIVE_METADATA, code, 0); goto done; }
    work.device = *d; work.read = read; work.disk_opaque = disk_opaque;
    work.mbr_source = mbr_source; work.mbr_opaque = mbr_opaque;
    if (capture(r) || binding(r, b)) { goto done; }
    first[0] = work.digest[0]; first[1] = work.digest[1]; reads = work.reads;
    code = rb_backup_stream(&r->stream, b, size, source, (void *)0, sink, sink_opaque);
    if (code) { fail(r, RB_LIVE_STREAM, code, 0); goto done; }
    if (capture(r) || binding(r, b)) { goto done; }
    if (work.digest[0] != first[0] || work.digest[1] != first[1] || work.reads != reads) {
        fail(r, RB_LIVE_CHANGED, 0, 0); goto done;
    }
    r->status = RB_LIVE_OK;
done:
    clear(&work, sizeof(work)); return r->status;
}
