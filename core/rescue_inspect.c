#include "rescue.h"
#include "config.h"

typedef struct {
    rb_sector_reader read;
    void *opaque;
    rb_u8 mbr[512];
} capture;

static void clear(void *p, rb_u16 size)
{
    rb_u8 *bytes = (rb_u8 *)p;
    while (size) { bytes[--size] = 0; }
}
static rb_u16 __cdecl captured_read(rb_u32 lba, rb_u8 *sector, void *opaque)
{
    capture *c = (capture *)opaque;
    rb_u16 i;
    if (lba) { return c->read(lba, sector, c->opaque); }
    for (i = 0; i < 512; ++i) { sector[i] = c->mbr[i]; }
    return 0;
}

void rb_rescue_inspect(rb_rescue_result *r, const rb_rescue_device *device,
                       rb_sector_reader read, void *opaque)
{
    capture c;
    rb_partition_scan scan;
    rb_u8 final_mbr[512];
    rb_u16 i;
    clear(r, sizeof(*r));
    if (device->drive != 0x80 || device->mode > 1
            || (!device->capacity_low && !device->capacity_high)) {
        r->status = RB_RESCUE_PARAMS; return;
    }
    if (!device->mode && (!device->heads || device->heads > 256
            || !device->sectors_per_track || device->sectors_per_track > 63
            || device->capacity_high || device->capacity_low
                > (rb_u32)device->heads * device->sectors_per_track * 1024UL)) {
        r->status = RB_RESCUE_GEOMETRY; return;
    }
    if (read(0, c.mbr, opaque)) { r->status = RB_RESCUE_IO; return; }
    c.read = read; c.opaque = opaque;
    r->disk_id = (rb_u32)c.mbr[440] | ((rb_u32)c.mbr[441] << 8)
        | ((rb_u32)c.mbr[442] << 16) | ((rb_u32)c.mbr[443] << 24);
    r->mbr_crc = rb_crc32(c.mbr, 512);
    r->signature = c.mbr[510] | ((rb_u16)c.mbr[511] << 8);
    r->marker = c.mbr[432] == 'R' && c.mbr[433] == 'B'
        && c.mbr[434] == 'M' && c.mbr[435] == '1';
    /* The supplied ID is the observed value, not backup/media authentication. */
    r->layout = rb_scan_partitions(&scan, captured_read, &c,
        device->capacity_low, device->capacity_high, r->disk_id);
    r->error_lba = scan.error_lba;
    if (!r->layout) { r->entries = scan.count; r->ebrs = scan.ebr_count; }
    if (read(0, final_mbr, opaque)) {
        clear(r, sizeof(*r)); r->status = RB_RESCUE_IO; return;
    }
    for (i = 0; i < 512; ++i) {
        if (final_mbr[i] != c.mbr[i]) {
            clear(r, sizeof(*r)); r->status = RB_RESCUE_CHANGED; return;
        }
    }
}
