#ifndef RB_FAT_REVIEW_H
#define RB_FAT_REVIEW_H

#include "fat_plan.h"
#include "ide_pair.h"

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

enum { NO_DEVICE = RB_FORMAT_CLUSTER_COUNT + 1, BAD_TABLE, READ_ERROR, CHANGED };
rb_u16 __cdecl rb_fat_cached_read(rb_u32 lba, rb_u8 *sector, void *opaque);
rb_u16 rb_fat_observe(observation *s, rb_u16 slot, rb_u16 spc);
void rb_fat_hex32(rb_u32 value);
void rb_fat_span(const char *name, rb_u32 begin, rb_u32 end);
rb_u32 rb_fat_metadata_last(const rb_fat_plan *plan);
const char *rb_format_check_tables(const observation *v, rb_format_comparison *r);

const char *rb_format_compare(const observation *view, rb_format_comparison *result);

#endif
