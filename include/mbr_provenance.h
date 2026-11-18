#ifndef RB_MBR_PROVENANCE_H
#define RB_MBR_PROVENANCE_H

#include "backup.h"

/* In-memory contracts, never an on-disk format. The installer/recovery caller
   supplies independently enrolled identities and exclusive access. */
typedef struct {
    rb_u8 id[16];
    rb_u32 capacity_low, capacity_high;
} rb_mbr_target;

typedef struct {
    rb_mbr_target target;
    rb_u8 recovery_id[16];
} rb_mbr_binding;

/* Identifies the exact pending observation presented for a decision. */
typedef struct {
    rb_mbr_binding binding;
    rb_u32 revision;
} rb_mbr_review_ticket;

/* Metadata and full sector decoded from the independent recovery record. */
typedef struct {
    rb_mbr_binding binding;
    rb_u32 revision;
    rb_u16 role;
    rb_u8 sector[512];
} rb_mbr_record;

/* Each acquisition returns the actual sector byte count (512 on success,
   zero on I/O failure) and reports its independently identified physical
   endpoint. The medium ID is separate from the tags inside the file. */
typedef rb_u16 (__cdecl *rb_mbr_current_reader)(rb_mbr_target *actual, rb_u8 *sector, void *opaque);
typedef rb_u16 (__cdecl *rb_mbr_record_reader)(rb_u16 role, rb_u32 revision,
    rb_mbr_record *record, rb_u8 *actual_medium_id, void *opaque);

typedef struct {
    const rb_mbr_binding *binding;
    rb_mbr_current_reader current;
    void *disk;
    rb_mbr_record_reader external;
    void *medium;
} rb_mbr_io;

/* Trusted, zero-initialized state for one enrollment. A recovery file alone
   cannot initialize it. Revision 1 seals the original. Each successful review
   advances the revision, including reviews of identical bytes. */
typedef struct {
    rb_mbr_binding binding;
    rb_u32 revision, approved_revision;
    rb_u16 pending;
    rb_u8 original[512], candidate[512], approved[512];
} rb_mbr_history;

enum { RB_MBR_ORIGIN_UNKNOWN, RB_MBR_FIRST_INSTALL, RB_MBR_ALREADY_MANAGED };
enum { RB_MBR_NO_DECISION, RB_MBR_REJECT, RB_MBR_APPROVE };
enum {
    RB_MBR_OK, RB_MBR_PARAMS, RB_MBR_ORIGIN, RB_MBR_BINDING, RB_MBR_STATE,
    RB_MBR_REVISION, RB_MBR_LIVE_IO, RB_MBR_EXTERNAL_IO, RB_MBR_ROLE, RB_MBR_CHANGED
};

/* Synchronous operations with stable inputs, disjoint buffers and no concurrent
   callbacks or mutations of history. Only the operations below modify history.
   The caller obtains FIRST_INSTALL from the pre-write installation workflow. */
rb_u16 rb_mbr_enroll(rb_mbr_history *history, const rb_mbr_io *io, rb_u16 origin);
rb_u16 rb_mbr_review(rb_mbr_history *history, const rb_mbr_io *io, rb_mbr_review_ticket *ticket);
rb_u16 rb_mbr_decide(rb_mbr_history *history, const rb_mbr_io *io,
                     const rb_mbr_review_ticket *ticket, rb_u16 decision);
/* Return exact original/last-approved bytes only after independent readback.
   The requested revision must be current for that role. Any failure clears the
   512-byte output, when supplied. This never authorizes a restore. */
rb_u16 rb_mbr_read_role(const rb_mbr_history *history, const rb_mbr_io *io,
                        rb_u16 role, rb_u32 revision, rb_u8 *out);

#endif
