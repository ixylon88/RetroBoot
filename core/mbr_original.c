#include "mbr_original.h"
#include "mbr_current.h"
#include "mbr_header.h"

static const rb_u8 blank[512] = {0};

static rb_u16 read_carrier(const rb_mbr_original_io *io, const rb_u8 *id,
                           rb_u16 sector, rb_u8 *out)
{
    rb_u8 actual[16] = {0};
    if (io->read(sector, out, actual, io->carrier) != 512) { return RB_MBR_EXTERNAL_IO; }
    return equal(actual, id, 16) ? RB_MBR_OK : RB_MBR_BINDING;
}

static rb_u16 verify_carrier(const rb_mbr_original_io *io, const rb_u8 *id,
                             rb_u16 sector, const rb_u8 *expected)
{
    rb_u8 data[512];
    rb_u16 rc = read_carrier(io, id, sector, data);
    if (rc) { return rc; }
    return equal(data, expected, 512) ? RB_MBR_OK : RB_MBR_CHANGED;
}

static rb_u16 verify_disk(const rb_mbr_original_io *io, const rb_mbr_target *target,
                          const rb_u8 *original)
{
    rb_u8 current[512];
    rb_u16 rc = read_bound_mbr(target, io->current, io->disk, current);
    if (rc) { return rc; }
    return equal(current, original, 512) ? RB_MBR_OK : RB_MBR_CHANGED;
}

rb_u16 rb_mbr_capture_original(const rb_mbr_binding *b, rb_u16 origin,
                               const rb_mbr_original_io *io)
{
    rb_mbr_commit first = {1, 1, 0, 0, 0, 0};
    rb_u8 original[512], header[512], sector[512];
    rb_u16 rc, n;
    int sealed, matches;
    if (!b || !io || !io->current || !io->read || !io->write) { return RB_MBR_PARAMS; }
    if (origin != RB_MBR_FIRST_INSTALL) { return RB_MBR_ORIGIN; }
    if (!valid_binding(b)) { return RB_MBR_BINDING; }
    rc = read_bound_mbr(&b->target, io->current, io->disk, original);
    if (rc) { return rc; }
    if (equal(original + 432, (const rb_u8 *)"RBM1", 4)) { return RB_MBR_ORIGIN; }

    first.original_crc = rb_crc32(original, 512);
    make_header(header, "RBORG001", b, &first);
    rc = read_carrier(io, b->recovery_id, 0, sector);
    if (rc) { return rc; }
    sealed = equal(sector, header, 512);
    if (!sealed && !equal(sector, blank, 512)) { return RB_MBR_STATE; }
    rc = read_carrier(io, b->recovery_id, 1, sector);
    if (rc) { return rc; }
    matches = equal(sector, original, 512);
    if (!matches && (sealed || !equal(sector, blank, 512))) { return RB_MBR_CHANGED; }

    if (!sealed) {
        /* A missing header on a carrier with later history is never virgin. */
        for (n = 2; n < 6; ++n) {
            rc = verify_carrier(io, b->recovery_id, n, blank);
            if (rc) { return rc; }
        }
        if (!matches && io->write(1, original, b->recovery_id, io->carrier) != 512) {
            return RB_MBR_EXTERNAL_IO;
        }
        rc = verify_carrier(io, b->recovery_id, 1, original);
        if (!rc) { rc = verify_disk(io, &b->target, original); }
        if (!rc) { rc = verify_carrier(io, b->recovery_id, 0, blank); }
        if (rc) { return rc; }
        if (io->write(0, header, b->recovery_id, io->carrier) != 512) {
            return RB_MBR_EXTERNAL_IO;
        }
    }
    rc = verify_carrier(io, b->recovery_id, 0, header);
    if (!rc) { rc = verify_carrier(io, b->recovery_id, 1, original); }
    if (!rc) { rc = verify_disk(io, &b->target, original); }
    return rc;
}
