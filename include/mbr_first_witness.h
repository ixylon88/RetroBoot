#ifndef RB_MBR_FIRST_WITNESS_H
#define RB_MBR_FIRST_WITNESS_H

#include "mbr_exchange.h"

enum { RB_FIRST_WITNESS_ORIGIN = RB_REOPEN_CHANGED + 1 };

/* The caller retains exclusive first-install custody of the target, its sealed
   original and the separately provisioned witness. All three IDs are distinct.
   Success publishes generation 1, original revision 1, with no approved sector.
   Cold verification uses rb_mbr_load_witness and rb_mbr_reopen without a target.
   An ambiguous completion may already have published the header. */
rb_u16 rb_mbr_publish_first_witness(const rb_mbr_binding *binding, const rb_u8 *witness_id,
                                    rb_u16 origin, rb_mbr_current_reader current, void *disk,
                                    const rb_mbr_exchange *media);

#endif
