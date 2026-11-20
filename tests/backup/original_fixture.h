#ifndef RB_ORIGINAL_FIXTURE_H
#define RB_ORIGINAL_FIXTURE_H

#include "mbr_provenance.h"
#include "rescue.h"
#include "rescue_file.h"
#include "bios_ui.h"
#include "config.h"
#include "mbr_floppy.h"
#include "mbr_fixture.h"

/* A disposable, externally provisioned VM pair. The target label is outside
   its MBR, at the end of this known disk. The test cannot enroll arbitrary
   disks or establish first-install custody from a label. */
#define TARGET_SECTORS 10080UL
static const rb_u8 target_id[16] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x61};
static const rb_u8 carrier_id[16] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x62};

static int target_matches(rb_rescue_device *device)
{
    rb_u8 readback[512];
    return !rb_rescue_probe(device) && device->capacity_low == TARGET_SECTORS
        && !device->capacity_high && !rb_disk_read(TARGET_SECTORS - 1, readback, 0)
        && rb_mbr_label_matches(readback, target_id);
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

#endif
