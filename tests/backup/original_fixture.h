#ifndef RB_ORIGINAL_FIXTURE_H
#define RB_ORIGINAL_FIXTURE_H

#include "mbr_provenance.h"
#include "rescue.h"
#include "rescue_file.h"
#include "bios_ui.h"
#include "config.h"
#include "mbr_fixture.h"

/* A disposable, externally provisioned VM pair. The target label is outside
   its MBR, at the end of this known disk. The test cannot enroll arbitrary
   disks or establish first-install custody from a label. */
typedef struct {
    rb_u16 drive, base, sectors;
    const rb_u8 *id;
} capture_medium;

#define TARGET_SECTORS 10080UL
static const rb_u8 target_id[16] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x61};
static const rb_u8 carrier_id[16] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x62};

rb_u16 __cdecl rb_fixture_floppy_write(rb_u32 lba, const rb_u8 *in, void *boot_drive);

static int label_matches(const rb_u8 *bytes, const rb_u8 *id)
{
    rb_u16 i;
    rb_u32 crc = rb_crc32(bytes, 508);
    for (i = 0; i < 4; ++i) {
        if (bytes[508 + i] != (rb_u8)(crc >> (8 * i))) { return 0; }
    }
    return same(bytes, (const rb_u8 *)"RBMEDIA1", 8) && same(bytes + 8, id, 16)
        && empty(bytes + 24, 484);
}

static int target_matches(rb_rescue_device *device)
{
    rb_u8 readback[512];
    return !rb_rescue_probe(device) && device->capacity_low == TARGET_SECTORS
        && !device->capacity_high && !rb_disk_read(TARGET_SECTORS - 1, readback, 0)
        && label_matches(readback, target_id);
}

static rb_u16 __cdecl read_target(rb_mbr_target *actual, rb_u8 *out, void *opaque)
{
    rb_rescue_device device;
    (void)opaque;
    if (!target_matches(&device) || rb_disk_read(0, out, 0)
        || !target_matches(&device)) { return 0; }
    copy(actual->id, target_id, 16);
    actual->capacity_low = device.capacity_low;
    actual->capacity_high = device.capacity_high;
    return 512;
}

static void capture_binding(rb_mbr_binding *b)
{
    copy(b->target.id, target_id, 16);
    b->target.capacity_low = TARGET_SECTORS;
    b->target.capacity_high = 0;
    copy(b->recovery_id, carrier_id, 16);
}

static int medium_matches(capture_medium *medium)
{
    rb_u8 bytes[512];
    return !rb_floppy_read(medium->base, bytes, &medium->drive) && label_matches(bytes, medium->id);
}

static rb_u16 __cdecl read_record(rb_u16 n, rb_u8 *out, rb_u8 *id, void *opaque)
{
    capture_medium *m = (capture_medium *)opaque;
    if (n >= m->sectors || !medium_matches(m) || rb_floppy_read(m->base + 1 + n, out, &m->drive)
        || !medium_matches(m)) { return 0; }
    copy(id, m->id, 16);
    return 512;
}

#endif
