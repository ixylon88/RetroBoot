#include "mbr_publication.h"
#include "mbr_header.h"
#include "mbr_media.h"

rb_u16 rb_mbr_stage_checkpoint(const rb_mbr_exchange *io, const rb_mbr_restart_source *s,
                               const rb_mbr_witness *old, const rb_mbr_witness *next)
{
    rb_u8 header[512];
    const rb_u8 *id = old->binding.recovery_id;
    rb_u16 slot = (next->commit.generation & 1) ? 2 : 4;
    rb_u16 rc = rb_mbr_verify_carrier(old, s);
    if (rc) { return rc; }
    rc = write_checked(io, slot + 1, next->approved, id);
    if (rc) { return rc; }
    make_header(header, "RBCMT001", &next->binding, &next->commit);
    rc = write_checked(io, slot, header, id);
    if (rc) { return rc; }
    return rb_mbr_verify_carrier(next, s);
}

rb_u16 rb_mbr_reserve_checkpoint(rb_mbr_witness *next, const rb_mbr_binding *b, const rb_u8 *id,
                                 const rb_mbr_exchange *io, rb_u16 generations_needed)
{
    rb_mbr_witness old;
    rb_mbr_restart_source source;
    rb_u8 header[512];
    rb_u16 rc;
    if (!b || !id || !io || !io->select || !io->read || !io->write) { return RB_REOPEN_PARAMS; }
    source.read = io->read;
    source.opaque = io->opaque;
    if (io->select(RB_RESERVE_START, io->opaque)) { return RB_REOPEN_IO; }
    rc = rb_mbr_load_witness(&old, b, id, &source);
    if (rc) { return rc; }
    if (old.commit.generation > 0xffffffffUL - generations_needed || old.commit.issued == 0xffffffffUL) {
        return RB_RESERVE_FULL;
    }
    *next = old;
    ++next->commit.generation;
    ++next->commit.issued;
    if (io->select(RB_RESERVE_DATA, io->opaque)) { return RB_REOPEN_IO; }
    rc = rb_mbr_stage_checkpoint(io, &source, &old, next);
    if (rc) { return rc; }
    if (io->select(RB_RESERVE_RETURN, io->opaque)) { return RB_REOPEN_IO; }
    rc = rb_mbr_verify_witness(&old, id, &source);
    if (rc) { return rc; }
    make_witness_header(header, next);
    rc = write_checked(io, 0, header, id);
    if (rc) { return rc; }
    return rb_mbr_verify_witness(next, id, &source);
}

rb_u16 rb_mbr_reserve_number(rb_u32 *number, const rb_mbr_binding *b, const rb_u8 *id,
                             const rb_mbr_reservation_io *io)
{
    rb_mbr_witness next;
    rb_u16 rc;
    if (!number) { return RB_REOPEN_PARAMS; }
    *number = 0;
    rc = rb_mbr_reserve_checkpoint(&next, b, id, io, 1);
    if (!rc) { *number = next.commit.issued; }
    return rc;
}
