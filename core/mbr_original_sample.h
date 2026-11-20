#ifndef RB_MBR_ORIGINAL_SAMPLE_H
#define RB_MBR_ORIGINAL_SAMPLE_H

#include "mbr_original.h"

/* Internal to the two first-install entry points. The supplied sample is
   retained across medium exchange; every later read must match it exactly. */
rb_u16 rb_mbr_seal_original_sample(const rb_mbr_binding *binding, const rb_u8 *original,
                                   const rb_mbr_original_io *io);
#endif
