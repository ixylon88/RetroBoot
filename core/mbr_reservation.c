#include "mbr_reservation.h"
#include "mbr_compare.h"
#include "config.h"

static void put32(rb_u8 *out, rb_u32 v)
{
    rb_u16 i;
    for (i = 0; i < 4; ++i) {
        out[i] = (rb_u8)v;
        v >>= 8;
    }
}

static void make_header(rb_u8 *out, const char *tag, const rb_mbr_witness *w)
{
    rb_u16 i;
    const rb_mbr_commit *c = &w->commit;
    clear(out, 512);
    for (i = 0; i < 8; ++i) { out[i] = (rb_u8)tag[i]; }
    for (i = 0; i < 16; ++i) {
        out[8 + i] = w->binding.target.id[i];
        out[32 + i] = w->binding.recovery_id[i];
    }
    put32(out + 24, w->binding.target.capacity_low);
    put32(out + 28, w->binding.target.capacity_high);
    put32(out + 48, c->generation);
    put32(out + 52, c->issued);
    put32(out + 56, c->approved);
    put32(out + 60, c->previous);
    put32(out + 64, c->original_crc);
    put32(out + 68, c->approved_crc);
    put32(out + 508, rb_crc32(out, 508));
}

static rb_u16 write_checked(const rb_mbr_reservation_io *io, rb_u16 sector,
                            const rb_u8 *bytes, const rb_u8 *endpoint)
{
    rb_u8 readback[512], actual[16] = {0};
    if (io->write(sector, bytes, endpoint, io->opaque) != 512
        || io->read(sector, readback, actual, io->opaque) != 512) { return RB_REOPEN_IO; }
    if (!equal(actual, endpoint, 16)) { return RB_REOPEN_BINDING; }
    return equal(bytes, readback, 512) ? RB_REOPEN_OK : RB_REOPEN_CHANGED;
}

static rb_u16 stage(const rb_mbr_reservation_io *io, const rb_mbr_restart_source *s,
                    const rb_mbr_witness *old, const rb_mbr_witness *next)
{
    rb_mbr_recovered check;
    rb_u8 header[512];
    const rb_u8 *id = old->binding.recovery_id;
    rb_u16 slot = (next->commit.generation & 1) ? 2 : 4;
    rb_u16 rc = rb_mbr_reopen(&check, old, s);
    if (rc) { return rc; }
    rc = write_checked(io, slot + 1, next->approved, id);
    if (rc) { return rc; }
    make_header(header, "RBCMT001", next);
    rc = write_checked(io, slot, header, id);
    if (rc) { return rc; }
    return rb_mbr_reopen(&check, next, s);
}

/* Both loads check the same external binding, the canonical record and its
   CRCs. The full sector comparisons also cover distinct equal-CRC payloads. */
static rb_u16 require_witness(const rb_mbr_witness *expected, const rb_u8 *id,
                              const rb_mbr_restart_source *s)
{
    rb_mbr_witness actual;
    const rb_mbr_commit *a = &actual.commit, *e = &expected->commit;
    rb_u16 rc = rb_mbr_load_witness(&actual, &expected->binding, id, s);
    if (rc) { return rc; }
    if (a->generation != e->generation || a->issued != e->issued
        || a->approved != e->approved || a->previous != e->previous
        || !equal(actual.original, expected->original, 512)
        || !equal(actual.approved, expected->approved, 512)) { return RB_REOPEN_CHANGED; }
    return RB_REOPEN_OK;
}

rb_u16 rb_mbr_reserve_number(rb_u32 *number, const rb_mbr_binding *b, const rb_u8 *id,
                             const rb_mbr_reservation_io *io)
{
    rb_mbr_witness old, next;
    rb_mbr_restart_source source;
    rb_u8 header[512];
    rb_u16 rc;
    if (!number) { return RB_REOPEN_PARAMS; }
    *number = 0;
    if (!b || !id || !io || !io->select || !io->read || !io->write) { return RB_REOPEN_PARAMS; }
    source.read = io->read;
    source.opaque = io->opaque;
    if (io->select(RB_RESERVE_START, io->opaque)) { return RB_REOPEN_IO; }
    rc = rb_mbr_load_witness(&old, b, id, &source);
    if (rc) { return rc; }
    if (old.commit.generation == 0xffffffffUL || old.commit.issued == 0xffffffffUL) {
        return RB_RESERVE_FULL;
    }
    next = old;
    ++next.commit.generation;
    ++next.commit.issued;
    if (io->select(RB_RESERVE_DATA, io->opaque)) { return RB_REOPEN_IO; }
    rc = stage(io, &source, &old, &next);
    if (rc) { return rc; }
    if (io->select(RB_RESERVE_RETURN, io->opaque)) { return RB_REOPEN_IO; }
    rc = require_witness(&old, id, &source);
    if (rc) { return rc; }
    make_header(header, "RBWIT001", &next);
    rc = write_checked(io, 0, header, id);
    if (rc) { return rc; }
    rc = require_witness(&next, id, &source);
    if (!rc) { *number = next.commit.issued; }
    return rc;
}
