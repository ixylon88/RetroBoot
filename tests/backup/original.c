#include "mbr_original.h"
#include "original_fixture.h"

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
    io.read = rb_mbr_floppy_read;
    io.write = rb_mbr_floppy_save_original;
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
