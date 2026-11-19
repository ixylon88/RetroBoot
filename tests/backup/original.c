#include "mbr_original.h"
#include "original_fixture.h"

static rb_u16 __cdecl write_record(rb_u16 n, const rb_u8 *in, const rb_u8 *id, void *opaque)
{
    capture_medium *m = (capture_medium *)opaque;
    if (n > 1 || !same(id, carrier_id, 16) || !medium_matches(m)
        || rb_fixture_floppy_write(n + 1, in, &m->drive) || !medium_matches(m)) { return 0; }
    return 512;
}

rb_u16 __cdecl rb_mbr_original_demo(rb_u16 boot_drive)
{
    rb_mbr_original_io io;
    rb_mbr_binding binding;
    rb_u16 key, origin, rc;
    capture_medium carrier;
    carrier.drive = boot_drive;
    carrier.base = 0;
    carrier.sectors = 6;
    carrier.id = carrier_id;
    capture_binding(&binding);
    io.current = read_target;
    io.read = read_record;
    io.write = write_record;
    io.disk = 0;
    io.carrier = &carrier;

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
