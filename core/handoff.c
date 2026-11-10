#include "handoff.h"

typedef struct {
    rb_sector_reader read;
    void *opaque;
    rb_u32 lba;
    rb_u8 *capture;
} capturing_reader;

static rb_u16 __cdecl capture_read(rb_u32 lba, rb_u8 *sector, void *opaque)
{
    capturing_reader *source = (capturing_reader *)opaque;
    rb_u16 i, error = source->read(lba, sector, source->opaque);
    if (error == 0 && lba == source->lba) {
        for (i = 0; i < 512; ++i) { source->capture[i] = sector[i]; }
    }
    return error;
}

static rb_u16 fail(rb_handoff_buffer *r, rb_u16 status, rb_u16 detail)
{
    rb_u16 i;
    rb_u8 *bytes = (rb_u8 *)r;
    for (i = 0; i < sizeof(*r); ++i) { bytes[i] = 0; }
    r->status = status; r->detail = detail;
    return status;
}

rb_u16 rb_prepare_handoff(rb_handoff_buffer *r, const rb_handoff_target *target,
                         rb_sector_reader read, void *opaque, rb_u32 low, rb_u32 high)
{
    rb_partition_scan scan;
    rb_volume_probe volume;
    capturing_reader source;
    rb_partition *p;
    rb_u16 i, offset;
    fail(r, RB_HANDOFF_OK, 0);
    if (target->slot < 1 || target->slot > 4 || target->entry[0] != 0x80) {
        return fail(r, RB_HANDOFF_TARGET, 0);
    }
    source.read = read; source.opaque = opaque; source.lba = 0; source.capture = r->sector;
    if (rb_scan_partitions(&scan, capture_read, &source, low, high, target->disk_id) != 0) {
        return fail(r, RB_HANDOFF_SCAN, scan.status);
    }
    p = &scan.entries[target->slot - 1];
    if (p->logical || p->flag != 0x80 || (p->type != 0x06 && p->type != 0x0E
                                        && p->type != 0x0B && p->type != 0x0C)) {
        return fail(r, RB_HANDOFF_TARGET, 0);
    }
    offset = 446 + (target->slot - 1) * 16;
    for (i = 0; i < 16; ++i) {
        if (r->sector[offset + i] != target->entry[i]) { return fail(r, RB_HANDOFF_TARGET, 0); }
        r->entry[i] = r->sector[offset + i];
    }
    source.lba = p->start;
    /* Capture the exact read checked by the BPB parser: no unchecked reread. */
    if (rb_probe_volume(&volume, p, capture_read, &source, low, high) != 0) {
        return fail(r, RB_HANDOFF_VOLUME, volume.status);
    }
    for (i = 0; i < 512; ++i) {
        if (r->sector[i] != target->sector[i]) { return fail(r, RB_HANDOFF_CODE, 0); }
    }
    return RB_HANDOFF_OK;
}
