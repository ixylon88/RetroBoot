#ifndef RB_MBR_PUBLICATION_H
#define RB_MBR_PUBLICATION_H

#include "mbr_reservation.h"

/* Private publisher operations. A successful reservation leaves the witness
   selected. Only that call's returned checkpoint can supply a new review. */
rb_u16 rb_mbr_reserve_checkpoint(rb_mbr_witness *next, const rb_mbr_binding *binding,
                                 const rb_u8 *id, const rb_mbr_exchange *media,
                                 rb_u16 generations_needed);
rb_u16 rb_mbr_stage_checkpoint(const rb_mbr_exchange *media, const rb_mbr_restart_source *source,
                               const rb_mbr_witness *old, const rb_mbr_witness *next);

#endif
