#include "mbr_first_witness.h"
#include "mbr_current.h"
#include "mbr_header.h"
#include "mbr_media.h"

static const rb_u8 blank[512] = {0};

static rb_u16 sample(const rb_mbr_target *target, rb_mbr_current_reader read,
                     void *disk, rb_u8 *bytes)
{
    rb_u16 rc = read_bound_mbr(target, read, disk, bytes);
    if (rc == RB_MBR_BINDING) { return RB_REOPEN_BINDING; }
    return rc == RB_MBR_OK ? RB_REOPEN_OK : RB_REOPEN_IO;
}

static rb_u16 verify_target(const rb_mbr_witness *first, rb_mbr_current_reader read, void *disk)
{
    rb_u8 bytes[512];
    rb_u16 rc = sample(&first->binding.target, read, disk, bytes);
    if (rc) { return rc; }
    return equal(bytes, first->original, 512) ? RB_REOPEN_OK : RB_REOPEN_CHANGED;
}

static rb_u16 expect(const rb_mbr_restart_source *s, const rb_u8 *id, rb_u16 sector,
                     const rb_u8 *expected)
{
    rb_u8 bytes[512];
    rb_u16 rc = acquire(s, id, sector, bytes);
    if (rc) { return rc; }
    return equal(bytes, expected, 512) ? RB_REOPEN_OK : RB_REOPEN_CHANGED;
}

/* A retry can continue from a complete staged payload. A nonzero header
   always closes enrollment, including after an ambiguous successful write. */
static rb_u16 pending_witness(const rb_mbr_restart_source *s, const rb_u8 *id,
                              const rb_u8 *original, int *staged)
{
    rb_u8 bytes[512];
    rb_u16 rc = expect(s, id, 0, blank);
    if (!rc) { rc = expect(s, id, 2, blank); }
    if (!rc) { rc = acquire(s, id, 1, bytes); }
    if (rc) { return rc; }
    *staged = equal(bytes, original, 512);
    return (*staged || equal(bytes, blank, 512)) ? RB_REOPEN_OK : RB_REOPEN_CHANGED;
}

static rb_u16 stage_carrier(const rb_mbr_witness *first, const rb_mbr_restart_source *s,
                            const rb_mbr_exchange *media, rb_mbr_current_reader read, void *disk)
{
    rb_mbr_recovered recovered;
    rb_u8 header[512], slot[512];
    const rb_u8 *id = first->binding.recovery_id;
    rb_u16 n, rc;
    make_header(header, "RBORG001", &first->binding, &first->commit);
    rc = expect(s, id, 0, header);
    if (!rc) { rc = expect(s, id, 1, first->original); }
    /* No approval in slot one and no later history in the alternate slot. */
    for (n = 3; !rc && n < 6; ++n) { rc = expect(s, id, n, blank); }
    if (!rc) { rc = acquire(s, id, 2, slot); }
    if (rc) { return rc; }

    make_header(header, "RBCMT001", &first->binding, &first->commit);
    if (!equal(slot, header, 512) && !equal(slot, blank, 512)) { return RB_REOPEN_STALE; }
    rc = verify_target(first, read, disk);
    if (!rc && !equal(slot, header, 512)) { rc = write_checked(media, 2, header, id); }
    if (rc) { return rc; }
    return rb_mbr_reopen(&recovered, first, s);
}

rb_u16 rb_mbr_publish_first_witness(const rb_mbr_binding *b, const rb_u8 *id,
                                    rb_u16 origin, rb_mbr_current_reader read, void *disk,
                                    const rb_mbr_exchange *media)
{
    rb_mbr_witness first;
    rb_mbr_restart_source source;
    rb_u8 header[512];
    rb_u16 rc;
    int staged, returned;
    if (!b || !id || !read || !media || !media->select || !media->read || !media->write) {
        return RB_REOPEN_PARAMS;
    }
    if (origin != RB_MBR_FIRST_INSTALL) { return RB_FIRST_WITNESS_ORIGIN; }
    if (!valid_witness_binding(b, id)) { return RB_REOPEN_BINDING; }
    source.read = media->read;
    source.opaque = media->opaque;
    clear((rb_u8 *)&first, sizeof(first));
    first.binding = *b;
    first.commit.generation = first.commit.issued = 1;
    if (media->select(RB_MBR_START_WITNESS, media->opaque)) { return RB_REOPEN_IO; }
    rc = sample(&b->target, read, disk, first.original);
    if (rc) { return rc; }
    if (equal(first.original + 432, (const rb_u8 *)"RBM1", 4)) { return RB_FIRST_WITNESS_ORIGIN; }
    first.commit.original_crc = rb_crc32(first.original, 512);
    rc = pending_witness(&source, id, first.original, &staged);
    if (rc) { return rc; }

    if (media->select(RB_MBR_SELECT_CARRIER, media->opaque)) { return RB_REOPEN_IO; }
    rc = stage_carrier(&first, &source, media, read, disk);
    if (rc) { return rc; }

    if (media->select(RB_MBR_RETURN_WITNESS, media->opaque)) { return RB_REOPEN_IO; }
    rc = pending_witness(&source, id, first.original, &returned);
    if (rc) { return rc; }
    if (returned != staged) { return RB_REOPEN_CHANGED; }
    if (!staged) { rc = write_checked(media, 1, first.original, id); }
    if (!rc) { rc = verify_target(&first, read, disk); }
    if (!rc) { rc = pending_witness(&source, id, first.original, &returned); }
    if (rc) { return rc; }
    if (!returned) { return RB_REOPEN_CHANGED; }
    make_header(header, "RBWIT001", b, &first.commit);
    rc = write_checked(media, 0, header, id);
    if (rc) { return rc; }
    return rb_mbr_verify_witness(&first, id, &source);
}
