/* Shared bounded operations for the native MBR history models. */
#ifndef RB_MBR_BYTES_H
#define RB_MBR_BYTES_H

#include "mbr_compare.h"

static __inline void copy_sector(rb_u8 *out, const rb_u8 *in)
{
    rb_u16 i;
    for (i = 0; i < 512; ++i) { out[i] = in[i]; }
}

static int same_target(const rb_mbr_target *a, const rb_mbr_target *b)
{
    return equal(a->id, b->id, 16) && a->capacity_low == b->capacity_low
        && a->capacity_high == b->capacity_high;
}

static __inline int same_binding(const rb_mbr_binding *a, const rb_mbr_binding *b)
{
    return same_target(&a->target, &b->target) && equal(a->recovery_id, b->recovery_id, 16);
}

static int valid_binding(const rb_mbr_binding *b)
{
    static const rb_u8 empty[16] = {0};
    return (b->target.capacity_low || b->target.capacity_high)
        && !equal(b->target.id, empty, 16) && !equal(b->recovery_id, empty, 16)
        && !equal(b->target.id, b->recovery_id, 16);
}

#endif
