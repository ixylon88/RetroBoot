#include "backup_verify.h"
#include "backup_boot.h"
#include "fingerprint.h"
#include "mbr_bytes.h"

typedef struct {
    const rb_backup_destination *destination;
    rb_u32 digest[2], position;
    rb_u16 error;
} rb_output_pass;

static rb_mbr_witness retained;
static rb_backup planned; /* The saved readers may reuse the caller's original claims storage. */

static rb_u16 fail(rb_backup_verified *r, rb_u16 status, rb_u16 detail)
{
    r->status = status; r->detail = detail;
    return status;
}

static int bound_source(const rb_backup_input *source, const rb_mbr_target *expected)
{
    rb_mbr_target actual;
    return !source->identify(&actual, source->opaque) && same_target(&actual, expected)
        && source->device.capacity_low == expected->capacity_low
        && source->device.capacity_high == expected->capacity_high;
}

static rb_u16 __cdecl mbr_role(rb_u16 kind, rb_u16 index, rb_u32 offset, rb_u8 *out, void *opaque)
{
    const rb_mbr_witness *w = (const rb_mbr_witness *)opaque;
    if (index || offset || (kind != RB_BACKUP_ORIGINAL && kind != RB_BACKUP_APPROVED)) { return 1; }
    copy_sector(out, kind == RB_BACKUP_ORIGINAL ? w->original : w->approved);
    return 0;
}

static rb_u16 __cdecl stage(rb_u32 pos, const rb_u8 *sector, void *opaque)
{
    rb_output_pass *p = (rb_output_pass *)opaque;
    if (p->destination->write(pos, sector, p->destination->opaque)) { return 1; }
    rb_fingerprint_sector(p->digest, pos, sector);
    return 0;
}

static rb_u16 __cdecl compare(rb_u32 pos, const rb_u8 *sector, void *opaque)
{
    rb_output_pass *p = (rb_output_pass *)opaque;
    rb_u8 saved[512];
    p->position = pos;
    if (p->destination->read(pos, saved, p->destination->opaque)) { p->error = RB_VERIFY_READ; }
    else if (!equal(sector, saved, 512)) { p->error = RB_VERIFY_DIFFER; }
    if (p->error) { return 1; }
    rb_fingerprint_sector(p->digest, pos, saved);
    return 0;
}

static rb_u16 reopen(const rb_backup_destination *d, rb_u32 sectors)
{
    rb_u32 actual = 0;
    if (d->reopen(&actual, d->opaque)) { return RB_VERIFY_OPEN; }
    return actual == sectors * 512UL ? RB_VERIFY_OK : RB_VERIFY_LENGTH;
}

static rb_u16 stream(rb_backup_verified *r, const rb_backup *claims, rb_u32 sectors,
    const rb_backup_input *source, rb_output_pass *p, rb_u16 replay)
{
    rb_backup_live_result live;
    rb_u16 rc = rb_backup_live_stream(&live, claims, sectors, &source->device,
        source->read, source->opaque, mbr_role, &retained, replay ? compare : stage, p);
    if (p->error) { r->error_sector = p->position; return fail(r, p->error, 0); }
    if (rc || live.stream.sectors != sectors) {
        r->nested = live.detail;
        r->error_sector = rc == RB_LIVE_STREAM ? live.stream.file_sector : live.error_lba;
        return fail(r, replay ? RB_VERIFY_REPLAY : RB_VERIFY_PRODUCER, rc);
    }
    return 0;
}

rb_u16 rb_backup_verify_live(rb_backup_verified *r, const rb_backup *claims,
    rb_u32 sectors, const rb_backup_input *source, const rb_backup_history *history,
    const rb_backup_destination *d)
{
    rb_output_pass written = {0}, checked = {0};
    rb_backup_boot saved;
    rb_u16 rc;
    if (!r) { return RB_VERIFY_PARAMS; }
    clear((rb_u8 *)r, sizeof(*r));
    if (!claims || !sectors || sectors > RB_BACKUP_SECTORS || !source || !source->read
        || !source->identify || !history || !history->binding || !history->witness_id
        || !history->witness.read || !history->carrier.read || !d || !d->write
        || !d->reopen || !d->read) { return fail(r, RB_VERIFY_PARAMS, 0); }
    if (!bound_source(source, &history->binding->target)) { return fail(r, RB_VERIFY_TARGET, 0); }
    rc = rb_mbr_load_witness(&retained, history->binding, history->witness_id, &history->witness);
    if (rc) { return fail(r, RB_VERIFY_WITNESS, rc); }
    rc = rb_mbr_verify_carrier(&retained, &history->carrier);
    if (rc) { return fail(r, RB_VERIFY_CARRIER, rc); }
    if (!retained.commit.approved) { return fail(r, RB_VERIFY_APPROVAL, 0); }

    planned = *claims;
    written.destination = checked.destination = d;
    if (stream(r, &planned, sectors, source, &written, 0)) { return r->status; }
    rc = reopen(d, sectors);
    if (rc) { return fail(r, rc, 0); }
    /* Includes the independent container, saved-record and FAT boot-area readers. */
    rb_backup_check_boot(&saved, d->read, d->opaque, sectors);
    if (saved.status) {
        r->nested = saved.detail; r->record_detail = saved.record_detail;
        r->error_sector = saved.error_lba;
        return fail(r, RB_VERIFY_SAVED, saved.status);
    }

    if (!bound_source(source, &history->binding->target)) { return fail(r, RB_VERIFY_TARGET, 0); }
    rc = reopen(d, sectors);
    if (rc) { return fail(r, rc, 0); }
    if (stream(r, &planned, sectors, source, &checked, 1)) { return r->status; }
    if (written.digest[0] != checked.digest[0] || written.digest[1] != checked.digest[1]) {
        return fail(r, RB_VERIFY_CHANGED, 0);
    }
    rc = rb_mbr_verify_carrier(&retained, &history->carrier);
    if (rc) { return fail(r, RB_VERIFY_CARRIER, rc); }
    rc = rb_mbr_verify_witness(&retained, history->witness_id, &history->witness);
    if (rc) { return fail(r, RB_VERIFY_WITNESS, rc); }
    if (!bound_source(source, &history->binding->target)) { return fail(r, RB_VERIFY_TARGET, 0); }
    r->sectors = sectors; r->approved_revision = retained.commit.approved;
    return RB_VERIFY_OK;
}
