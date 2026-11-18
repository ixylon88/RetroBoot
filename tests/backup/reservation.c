#include "mbr_reservation.h"
#include "rescue_file.h"
#include "bios_ui.h"
#include "config.h"
#include "mbr_fixture.h"

rb_u16 __cdecl rb_fixture_floppy_write(rb_u32 lba, const rb_u8 *in, void *boot_drive);

/* Only the two dedicated disposable images carry these endpoint labels.
   A read or write verifies the whole physical label before and after I/O. */
typedef struct {
    rb_u16 drive, base, sectors;
    rb_u8 label[512];
} fixture_drive;

static fixture_drive floppy;
static const rb_u8 witness_id[16] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x55};

static int label_matches(fixture_drive *d)
{
    rb_u8 actual[512];
    return !rb_floppy_read(d->base, actual, &d->drive) && same(actual, d->label, 512);
}

static rb_u16 __cdecl select_medium(rb_u16 phase, void *opaque)
{
    fixture_drive *d = (fixture_drive *)opaque;
    rb_u16 i, key;
    rb_u32 crc;
    if (phase != RB_RESERVE_START) {
        if (phase == RB_RESERVE_DATA) { line("INSERT DATA DISK AND PRESS ENTER TO RESERVE"); }
        else {
            line("STAGED DATA VERIFIED");
            line("REINSERT START DISK AND PRESS ENTER");
        }
        do {
            key = rb_key_poll();
            if (key == 0xffff) { rb_idle(); }
        } while ((key & 255) != 13);
    }
    d->base = phase == RB_RESERVE_DATA ? 0 : 2876;
    d->sectors = phase == RB_RESERVE_DATA ? 6 : 3;
    d->label[23] = phase == RB_RESERVE_DATA ? 0x44 : 0x55;
    crc = rb_crc32(d->label, 508);
    for (i = 0; i < 4; ++i) { d->label[508 + i] = (rb_u8)(crc >> (8 * i)); }
    return 0;
}

static rb_u16 __cdecl read_record(rb_u16 n, rb_u8 *out, rb_u8 *id, void *opaque)
{
    fixture_drive *d = (fixture_drive *)opaque;
    if (n >= d->sectors || !label_matches(d)
        || rb_floppy_read(d->base + 1 + n, out, &d->drive) || !label_matches(d)) { return 0; }
    copy(id, d->label + 8, 16);
    return 512;
}

static rb_u16 __cdecl write_record(rb_u16 n, const rb_u8 *in, const rb_u8 *id, void *opaque)
{
    fixture_drive *d = (fixture_drive *)opaque;
    if ((d->base ? n != 0 : (n < 2 || n > 5)) || !same(id, d->label + 8, 16)
        || !label_matches(d) || rb_fixture_floppy_write(d->base + 1 + n, in, &d->drive)
        || !label_matches(d)) { return 0; }
    return 512;
}

rb_u16 __cdecl rb_mbr_reserve_demo(rb_u16 boot_drive)
{
    static rb_mbr_binding binding;
    rb_mbr_reservation_io io;
    rb_u32 number;
    rb_u16 rc;
    floppy.drive = boot_drive;
    copy(floppy.label, (const rb_u8 *)"RBMEDIA1", 8);
    binding.target.id[15] = 0x11;
    binding.target.capacity_low = 262144UL;
    binding.target.capacity_high = 1;
    binding.recovery_id[15] = 0x44;
    io.select = select_medium;
    io.read = read_record;
    io.write = write_record;
    io.opaque = &floppy;
    line("RB MBR RESERVATION");
    rc = rb_mbr_reserve_number(&number, &binding, witness_id, &io);
    if (rc) {
        if (!empty(&number, sizeof(number))) { return 2; }
        if (rc == RB_RESERVE_FULL) { line("COUNTER EXHAUSTED"); }
        else if (rc == RB_REOPEN_STALE) { line("STALE CHECKPOINT"); }
        else { line("MEDIA CHECK FAILED"); }
        return 1;
    }
    count("RESERVED REVIEW ", number);
    return 0;
}
