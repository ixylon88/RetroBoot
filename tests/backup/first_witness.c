#include "mbr_first_witness.h"
#include "original_fixture.h"

static const rb_u8 witness_id[16] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x63};

static rb_u16 keypress(void)
{
    rb_u16 key;
    do {
        key = rb_key_poll();
        if (key == 0xffff) { rb_idle(); }
    } while (key == 0xffff);
    return key & 255;
}

static rb_u16 __cdecl select_medium(rb_u16 phase, void *opaque)
{
    capture_medium *m = (capture_medium *)opaque;
    rb_u16 key;
    if (phase != RB_MBR_START_WITNESS) {
        if (phase == RB_MBR_SELECT_CARRIER) { line("INSERT RECOVERY FLOPPY AND PRESS ENTER"); }
        else { line("REINSERT WITNESS FLOPPY AND PRESS ENTER"); }
        do { key = keypress(); } while (key != 13 && key != 27);
        if (key == 27) { return 1; }
    }
    m->base = phase == RB_MBR_SELECT_CARRIER ? 0 : 2876;
    m->sectors = phase == RB_MBR_SELECT_CARRIER ? 6 : 3;
    m->id = phase == RB_MBR_SELECT_CARRIER ? carrier_id : witness_id;
    return 0;
}

static rb_u16 __cdecl write_record(rb_u16 n, const rb_u8 *in, const rb_u8 *id, void *opaque)
{
    capture_medium *m = (capture_medium *)opaque;
    if ((m->base == 0 ? n != 2 : n > 1) || !same(id, m->id, 16)
        || !medium_matches(m) || rb_fixture_floppy_write(m->base + 1 + n, in, &m->drive)
        || !medium_matches(m)) { return 0; }
    return 512;
}

static rb_u16 verify_pair(const rb_mbr_binding *binding, capture_medium *medium)
{
    rb_mbr_witness witness;
    rb_mbr_recovered history;
    rb_mbr_restart_source source;
    rb_u16 rc;
    source.read = read_record;
    source.opaque = medium;
    select_medium(RB_MBR_START_WITNESS, medium);
    rc = rb_mbr_load_witness(&witness, binding, witness_id, &source);
    if (rc) { return rc; }
    if (select_medium(RB_MBR_SELECT_CARRIER, medium)) { return RB_REOPEN_IO; }
    return rb_mbr_reopen(&history, &witness, &source);
}

rb_u16 __cdecl rb_mbr_witness_demo(rb_u16 boot_drive)
{
    rb_mbr_binding binding;
    rb_mbr_exchange media;
    capture_medium medium;
    rb_u16 key, rc;
    capture_binding(&binding);
    medium.drive = boot_drive;
    line("RB FIRST MBR WITNESS");
    line("E FIRST INSTALL / V VERIFY / ESC CANCEL");
    do { key = keypress(); } while (key != 'e' && key != 'E' && key != 'v' && key != 'V' && key != 27);
    if (key == 'v' || key == 'V') {
        rc = verify_pair(&binding, &medium);
        if (!rc) { line("ORIGINAL REV 1 VERIFIED"); }
    } else {
        media.select = select_medium;
        media.read = read_record;
        media.write = write_record;
        media.opaque = &medium;
        rc = rb_mbr_publish_first_witness(&binding, witness_id,
            key == 27 ? RB_MBR_ORIGIN_UNKNOWN : RB_MBR_FIRST_INSTALL, read_target, 0, &media);
        if (!rc) { line("INITIAL WITNESS PUBLISHED"); }
    }
    if (rc) { count("WITNESS STATUS ", rc); return 1; }
    return 0;
}
