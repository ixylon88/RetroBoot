#ifndef RB_VOLUME_H
#define RB_VOLUME_H

#include "partitions.h"

enum {
    RB_VOLUME_OK, RB_VOLUME_IO, RB_VOLUME_SIGNATURE, RB_VOLUME_JUMP,
    RB_VOLUME_SECTOR, RB_VOLUME_CLUSTER, RB_VOLUME_RESERVED, RB_VOLUME_FATS,
    RB_VOLUME_ROOT, RB_VOLUME_TOTAL, RB_VOLUME_HIDDEN, RB_VOLUME_LAYOUT,
    RB_VOLUME_TYPE, RB_VOLUME_FAT_SIZE, RB_VOLUME_FAT32, RB_VOLUME_RANGE,
    RB_VOLUME_UNSUPPORTED, RB_VOLUME_MEDIA
};

typedef struct {
    rb_u16 status, fat_bits, cluster_bytes, fats;
    rb_u32 total_sectors, clusters, data_lba, fat_sectors;
} rb_volume_probe;

typedef char rb_check_volume_probe[(sizeof(rb_volume_probe) == 24) ? 1 : -1];

/* A caller must first validate the complete partition layout. This function
 * rechecks the selected extent, reads at most its first sector, and never
 * authorizes a boot. All derived fields stay zero on failure/unsupported. */
rb_u16 rb_probe_volume(rb_volume_probe *result, const rb_partition *partition,
                      rb_sector_reader read, void *opaque,
                      rb_u32 capacity_low, rb_u32 capacity_high);
rb_u16 __cdecl rb_volume_selftest(void);

#endif
