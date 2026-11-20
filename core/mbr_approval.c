#include "mbr_approval.h"
#include "mbr_publication.h"
#include "mbr_live_sample.h"
#include "mbr_header.h"
#include "mbr_media.h"

static rb_u16 review_reserved(const rb_mbr_witness *reserved, const rb_u8 *id,
                              rb_mbr_current_reader read, void *disk, const rb_mbr_exchange *media,
                              rb_mbr_decision decide, void *context)
{
    rb_mbr_witness next;
    rb_mbr_restart_source source;
    rb_u8 bytes[512];
    rb_u16 rc, decision, slot;
    source.read = media->read;
    source.opaque = media->opaque;
    next = *reserved;
    next.alternate_payload = !reserved->alternate_payload;
    slot = 2 + next.alternate_payload;
    /* A legacy three-sector endpoint can be verified but cannot stage an approval here. */
    rc = acquire(&source, id, slot, bytes);
    if (!rc) { rc = sample_mbr(&reserved->binding.target, read, disk, next.approved); }
    if (rc) { return rc; }
    decision = decide(reserved, next.approved, context);
    if (decision == RB_MBR_REJECT) { return RB_APPROVAL_REJECTED; }
    if (decision != RB_MBR_APPROVE) { return RB_APPROVAL_NO_DECISION; }

    ++next.commit.generation;
    next.commit.previous = reserved->commit.approved;
    next.commit.approved = reserved->commit.issued;
    next.commit.approved_crc = rb_crc32(next.approved, 512);
    rc = recheck_mbr(&reserved->binding.target, next.approved, read, disk);
    if (rc) { return rc; }
    if (media->select(RB_MBR_SELECT_CARRIER, media->opaque)) { return RB_REOPEN_IO; }
    rc = rb_mbr_stage_checkpoint(media, &source, reserved, &next);
    if (rc) { return rc; }

    if (media->select(RB_MBR_RETURN_WITNESS, media->opaque)) { return RB_REOPEN_IO; }
    rc = rb_mbr_verify_witness(reserved, id, &source);
    if (!rc) { rc = write_checked(media, slot, next.approved, id); }
    if (!rc) { rc = recheck_mbr(&reserved->binding.target, next.approved, read, disk); }
    if (!rc) { rc = rb_mbr_verify_witness(reserved, id, &source); }
    if (!rc) { rc = acquire(&source, id, slot, bytes); }
    if (rc) { return rc; }
    if (!equal(bytes, next.approved, 512)) { return RB_REOPEN_CHANGED; }
    make_witness_header(bytes, &next);
    rc = write_checked(media, 0, bytes, id);
    if (!rc) { rc = rb_mbr_verify_witness(&next, id, &source); }
    return rc;
}

rb_u16 rb_mbr_publish_review(rb_u32 *approved, const rb_mbr_binding *b, const rb_u8 *id,
                             rb_mbr_current_reader read, void *disk, const rb_mbr_exchange *media,
                             rb_mbr_decision decide, void *context)
{
    rb_mbr_witness reserved;
    rb_u16 rc;
    if (!approved) { return RB_REOPEN_PARAMS; }
    *approved = 0;
    if (!read || !decide) { return RB_REOPEN_PARAMS; }
    rc = rb_mbr_reserve_checkpoint(&reserved, b, id, media, 2);
    if (!rc) { rc = review_reserved(&reserved, id, read, disk, media, decide, context); }
    if (!rc) { *approved = reserved.commit.issued; }
    return rc;
}
