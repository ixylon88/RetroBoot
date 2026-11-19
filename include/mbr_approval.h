#ifndef RB_MBR_APPROVAL_H
#define RB_MBR_APPROVAL_H

#include "mbr_exchange.h"

enum { RB_APPROVAL_REJECTED = RB_REOPEN_CHANGED + 2, RB_APPROVAL_NO_DECISION };

/* The synchronous decision concerns this exact live sector and fresh revision.
   The UI has access to every reviewed byte and both historical roles.
   Only RB_MBR_APPROVE publishes. Neither input may be modified or retained. */
typedef rb_u16 (__cdecl *rb_mbr_decision)(const rb_mbr_witness *reserved,
                                         const rb_u8 *candidate, void *opaque);

/* One exclusive session owns the live target and both media. In addition to
   the legacy witness sectors 0..2, sector 3 must be separately allocated.
   The released revision is zero on failure or rejection. A durable number
   remains spent across either outcome. No target write callback is accepted. */
rb_u16 rb_mbr_publish_review(rb_u32 *approved, const rb_mbr_binding *binding, const rb_u8 *witness_id,
                             rb_mbr_current_reader read, void *disk, const rb_mbr_exchange *media,
                             rb_mbr_decision decide, void *decision_context);

#endif
