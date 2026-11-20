#include "mbr_floppy.h"
#include "rescue_file.h"
#include "config.h"
#include "mbr_compare.h"

int rb_mbr_label_matches(const rb_u8 *bytes, const rb_u8 *id)
{
    static const rb_u8 zero[484] = {0};
    rb_u16 i;
    rb_u32 crc = rb_crc32(bytes, 508);
    for (i = 0; i < 4; ++i) {
        if (bytes[508 + i] != (rb_u8)(crc >> (8 * i))) { return 0; }
    }
    return equal(bytes, (const rb_u8 *)"RBMEDIA1", 8) && equal(bytes + 8, id, 16)
        && equal(bytes + 24, zero, 484);
}

int rb_mbr_floppy_matches(capture_medium *medium)
{
    rb_u8 bytes[512];
    return !rb_floppy_read(medium->base, bytes, &medium->drive) && rb_mbr_label_matches(bytes, medium->id);
}

rb_u16 __cdecl rb_mbr_floppy_read(rb_u16 n, rb_u8 *out, rb_u8 *id, void *opaque)
{
    capture_medium *m = (capture_medium *)opaque;
    if (n >= m->sectors || !rb_mbr_floppy_matches(m) || rb_floppy_read(m->base + 1 + n, out, &m->drive)
        || !rb_mbr_floppy_matches(m)) { return 0; }
    for (n = 0; n < 16; ++n) { id[n] = m->id[n]; }
    return 512;
}

rb_u16 __cdecl rb_mbr_floppy_save_original(rb_u16 n, const rb_u8 *in, const rb_u8 *id, void *opaque)
{
    capture_medium *m = (capture_medium *)opaque;
    if (m->base || n > 1 || !equal(id, m->id, 16) || !rb_mbr_floppy_matches(m)
        || rb_fixture_floppy_write(n + 1, in, &m->drive) || !rb_mbr_floppy_matches(m)) { return 0; }
    return 512;
}
