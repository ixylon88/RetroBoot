#ifndef RB_MBR_RESTART_H
#define RB_MBR_RESTART_H

#include "mbr_provenance.h"

/* A reader returns the actual byte count and identifies the endpoint
   separately from the checkpoint it reads. Inputs and output are disjoint. */
typedef rb_u16 (__cdecl *rb_mbr_restart_reader)(rb_u16 sector, rb_u8 *out,
                                                rb_u8 *endpoint, void *opaque);
typedef struct {
    rb_mbr_restart_reader read;
    void *opaque;
} rb_mbr_restart_source;

typedef struct {
    rb_u32 generation, issued, approved, previous, original_crc, approved_crc;
} rb_mbr_commit;

/* Trusted in-memory result of reading the separately retained witness. */
typedef struct {
    rb_mbr_binding binding;
    rb_mbr_commit commit;
    rb_u8 original[512], approved[512];
} rb_mbr_witness;

/* A historical observation with no ticket-issuing or decision capability.
   Reopening the same checkpoint twice cannot reissue a review number. */
typedef struct {
    rb_mbr_binding binding;
    rb_u32 generation, issued, approved_revision;
    rb_u8 original[512], approved[512];
} rb_mbr_recovered;

enum { RB_REOPEN_OK, RB_REOPEN_PARAMS, RB_REOPEN_IO, RB_REOPEN_BINDING,
       RB_REOPEN_FORMAT, RB_REOPEN_CRC, RB_REOPEN_STALE, RB_REOPEN_CHANGED };

/* Enrollment and witness IDs come from trusted custody. A failure clears
   the entire witness. The caller keeps a successful witness immutable. */
rb_u16 rb_mbr_load_witness(rb_mbr_witness *out, const rb_mbr_binding *enrollment,
                           const rb_u8 *witness_id, const rb_mbr_restart_source *source);
/* Reload the retained witness and compare both complete sectors and all counters. */
rb_u16 rb_mbr_verify_witness(const rb_mbr_witness *expected, const rb_u8 *witness_id,
                             const rb_mbr_restart_source *source);
/* Cold-start destination. Failure clears all bytes and revision claims.
   Success recovers historical roles only. The target disk is never read. */
rb_u16 rb_mbr_reopen(rb_mbr_recovered *out, const rb_mbr_witness *witness,
                     const rb_mbr_restart_source *carrier);

#endif
