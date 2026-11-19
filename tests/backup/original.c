#include "mbr_original.h"
#include "rescue.h"
#include "rescue_file.h"
#include "bios_ui.h"
#include "config.h"
#include "mbr_fixture.h"

/* A disposable, externally provisioned VM pair. The target label is outside
   its MBR, at the end of this known disk. The test cannot enroll arbitrary
   disks or establish first-install custody from a label. */
#define TARGET_SECTORS 10080UL
static const rb_u8 target_id[16] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x61};
static const rb_u8 carrier_id[16] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x62};
static rb_u16 drive;

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

static int carrier_matches(void)
{
    rb_u8 readback[512];
    return !rb_floppy_read(0, readback, &drive) && label_matches(readback, carrier_id);
}

static rb_u16 __cdecl read_record(rb_u16 n, rb_u8 *out, rb_u8 *id, void *opaque)
{
    (void)opaque;
    if (n >= 6 || !carrier_matches() || rb_floppy_read(n + 1, out, &drive)
        || !carrier_matches()) { return 0; }
    copy(id, carrier_id, 16);
    return 512;
}

static rb_u16 __cdecl write_record(rb_u16 n, const rb_u8 *in, const rb_u8 *id, void *opaque)
{
    (void)opaque;
    if (n > 1 || !same(id, carrier_id, 16) || !carrier_matches()
        || rb_fixture_floppy_write(n + 1, in, &drive) || !carrier_matches()) { return 0; }
    return 512;
}

rb_u16 __cdecl rb_mbr_original_demo(rb_u16 boot_drive)
{
    rb_mbr_original_io io;
    rb_mbr_binding binding;
    rb_u16 key, origin, rc;
    drive = boot_drive;
    copy(binding.target.id, target_id, 16);
    binding.target.capacity_low = TARGET_SECTORS;
    binding.target.capacity_high = 0;
    copy(binding.recovery_id, carrier_id, 16);
    io.current = read_target;
    io.read = read_record;
    io.write = write_record;
    io.disk = io.carrier = 0;

    line("RB ORIGINAL MBR");
    line("INSERT RECOVERY FLOPPY");
    line("ENTER CONFIRMS FIRST INSTALL, ESC CANCELS");
    do {
        key = rb_key_poll() & 255;
        if (key == 255) { rb_idle(); }
    } while (key != 13 && key != 27);
    origin = key == 13 ? RB_MBR_FIRST_INSTALL : RB_MBR_ORIGIN_UNKNOWN;
    rc = rb_mbr_capture_original(&binding, origin, &io);
    if (rc) { count("CAPTURE STATUS ", rc); return 1; }
    line("ORIGINAL REV 1 VERIFIED");
    return 0;
}
