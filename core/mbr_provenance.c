#include "mbr_provenance.h"

#include "mbr_current.h"

static rb_u16 enrolled(const rb_mbr_history *h, const rb_mbr_io *io)
{
    if (!h || !io || !io->binding) { return RB_MBR_PARAMS; }
    if (!h->revision) { return RB_MBR_STATE; }
    return same_binding(&h->binding, io->binding) ? RB_MBR_OK : RB_MBR_BINDING;
}

static void forget_candidate(rb_mbr_history *h)
{
    h->pending = 0;
    clear(h->candidate, sizeof(h->candidate));
}

static rb_u16 check_external(const rb_mbr_io *io, rb_u16 role, rb_u32 revision,
                             const rb_u8 *expected)
{
    rb_mbr_record record;
    rb_u8 medium_id[16];
    clear(medium_id, sizeof(medium_id));
    clear((rb_u8 *)&record, sizeof(record));
    if (io->external(role, revision, &record, medium_id, io->medium) != sizeof(record.sector)) {
        return RB_MBR_EXTERNAL_IO;
    }
    if (!equal(medium_id, io->binding->recovery_id, 16) || !same_binding(&record.binding, io->binding)) {
        return RB_MBR_BINDING;
    }
    if (record.role != role) { return RB_MBR_ROLE; }
    if (record.revision != revision) { return RB_MBR_REVISION; }
    return equal(record.sector, expected, 512) ? RB_MBR_OK : RB_MBR_CHANGED;
}

static rb_u16 check_current(const rb_mbr_io *io, const rb_u8 *expected)
{
    rb_u8 sector[512];
    rb_u16 code = read_bound_mbr(&io->binding->target, io->current, io->disk, sector);
    if (code) { return code; }
    return equal(sector, expected, sizeof(sector)) ? RB_MBR_OK : RB_MBR_CHANGED;
}

rb_u16 rb_mbr_enroll(rb_mbr_history *h, const rb_mbr_io *io, rb_u16 origin)
{
    rb_u8 original[512];
    rb_u16 code;
    if (!h || !io || !io->binding || !io->current || !io->external) { return RB_MBR_PARAMS; }
    if (h->revision) { return RB_MBR_STATE; }
    if (origin != RB_MBR_FIRST_INSTALL) { return RB_MBR_ORIGIN; }
    if (!valid_binding(io->binding)) { return RB_MBR_BINDING; }
    code = read_bound_mbr(&io->binding->target, io->current, io->disk, original);
    if (code) { return code; }
    /* A known installed loader conflicts with the claimed first installation.
       An absent marker alone provides no positive evidence of origin. */
    if (equal(original + 432, (const rb_u8 *)"RBM1", 4)) { return RB_MBR_ORIGIN; }
    code = check_external(io, RB_BACKUP_ORIGINAL, 1, original);
    if (!code) { code = check_current(io, original); }
    if (code) { return code; }
    h->binding = *io->binding;
    copy_sector(h->original, original);
    h->revision = 1;
    return RB_MBR_OK;
}

rb_u16 rb_mbr_review(rb_mbr_history *h, const rb_mbr_io *io, rb_mbr_review_ticket *ticket)
{
    rb_u16 code;
    if (!ticket) { return RB_MBR_PARAMS; }
    clear((rb_u8 *)ticket, sizeof(*ticket));
    code = enrolled(h, io);
    if (code) { return code; }
    /* A fresh observation on the enrolled target invalidates the previous
       candidate even when the read fails or its revision cannot be advanced. */
    forget_candidate(h);
    if (!io->current) { return RB_MBR_PARAMS; }
    if (h->revision == 0xFFFFFFFFUL) { return RB_MBR_REVISION; }
    code = read_bound_mbr(&io->binding->target, io->current, io->disk, h->candidate);
    if (code) {
        clear(h->candidate, sizeof(h->candidate));
        return code;
    }
    ++h->revision;
    h->pending = 1;
    ticket->binding = h->binding;
    ticket->revision = h->revision;
    return RB_MBR_OK;
}

rb_u16 rb_mbr_decide(rb_mbr_history *h, const rb_mbr_io *io,
                     const rb_mbr_review_ticket *ticket, rb_u16 decision)
{
    rb_u16 code = enrolled(h, io);
    if (code) { return code; }
    if (!ticket) { return RB_MBR_PARAMS; }
    if (!h->pending) { return RB_MBR_STATE; }
    if (!same_binding(&ticket->binding, &h->binding)) { return RB_MBR_BINDING; }
    if (ticket->revision != h->revision) { return RB_MBR_REVISION; }
    if (decision == RB_MBR_REJECT) {
        forget_candidate(h);
        return RB_MBR_OK;
    }
    if (decision != RB_MBR_APPROVE) { return RB_MBR_PARAMS; }
    if (!io->current || !io->external) { code = RB_MBR_PARAMS; }
    else {
        code = check_current(io, h->candidate);
        if (!code) { code = check_external(io, RB_BACKUP_APPROVED, ticket->revision, h->candidate); }
        if (!code) { code = check_current(io, h->candidate); }
    }
    if (!code) {
        copy_sector(h->approved, h->candidate);
        h->approved_revision = ticket->revision;
    }
    /* A failed explicit approval must return to a fresh review. */
    forget_candidate(h);
    return code;
}

rb_u16 rb_mbr_read_role(const rb_mbr_history *h, const rb_mbr_io *io,
                        rb_u16 role, rb_u32 revision, rb_u8 *out)
{
    const rb_u8 *expected;
    rb_u16 code;
    if (!out) { return RB_MBR_PARAMS; }
    clear(out, 512);
    code = enrolled(h, io);
    if (code) { return code; }
    if (!io->external) { return RB_MBR_PARAMS; }
    if (role == RB_BACKUP_ORIGINAL) {
        if (revision != 1) { return RB_MBR_REVISION; }
        expected = h->original;
    } else if (role == RB_BACKUP_APPROVED) {
        if (!h->approved_revision) { return RB_MBR_STATE; }
        if (revision != h->approved_revision) { return RB_MBR_REVISION; }
        expected = h->approved;
    } else { return RB_MBR_ROLE; }
    code = check_external(io, role, revision, expected);
    if (!code) { copy_sector(out, expected); }
    return code;
}
