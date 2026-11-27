#ifndef RB_FAT_REVIEW_H
#define RB_FAT_REVIEW_H

#include "fat_plan.h"

typedef struct {
    rb_u32 lba;
    rb_u8 bytes[512];
} sector_copy;

typedef struct {
    rb_rescue_device disk;
    rb_u16 geometry[3];
    rb_partition_scan scan;
    sector_copy mbr, boot;
    rb_fat_plan plan;
} observation;

typedef struct {
    rb_u32 last, nonzero, fingerprint[2], error_lba;
} rb_format_comparison;

#define RB_FORMAT_NO_LBA 0xFFFFFFFFUL

/* A blank profile enables the usual standalone preview. */
int rb_format_load_pair(rb_u16 drive);
void rb_format_print_pair(void);
const char *rb_format_compare(const observation *view, rb_format_comparison *result);

#endif
