#ifndef RB_FAT_PLAN_H
#define RB_FAT_PLAN_H

#include "rescue.h"

enum { RB_FORMAT_OK, RB_FORMAT_TARGET, RB_FORMAT_RANGE, RB_FORMAT_CHS, RB_FORMAT_EDD,
       RB_FORMAT_CLUSTER_SIZE, RB_FORMAT_CLUSTER_COUNT };

typedef struct {
    rb_u16 bits, spc, reserved;
    rb_u32 sectors_per_fat, clusters, fat1, fat2, root, data;
} rb_fat_plan;

/* The caller supplies a primary from a complete validated MBR/EBR scan and
   its original 16-byte entry. Geometry is the live INT 13h/08h C/H/S count.
   A requested cluster size of zero selects a default. No sector I/O. */
rb_u16 rb_plan_primary_fat(rb_fat_plan *out, const rb_partition *part, const rb_u8 *entry,
    const rb_rescue_device *disk, const rb_u16 *geometry, rb_u16 spc);

#endif
