#ifndef RB_PARTITIONS_H
#define RB_PARTITIONS_H

#include "abi.h"

#define RB_SCAN_EBRS 16U
#define RB_SCAN_PARTITIONS (4U + RB_SCAN_EBRS)

enum {
    RB_SCAN_OK, RB_SCAN_IO, RB_SCAN_SIGNATURE, RB_SCAN_IDENTITY,
    RB_SCAN_FLAGS, RB_SCAN_TYPE, RB_SCAN_EMPTY, RB_SCAN_OVERFLOW,
    RB_SCAN_RANGE, RB_SCAN_OVERLAP, RB_SCAN_EXTENDED, RB_SCAN_SLOTS,
    RB_SCAN_LOOP, RB_SCAN_LIMIT
};

typedef struct {
    rb_u32 start, sectors, table_lba;
    rb_u16 type, flag, slot, logical;
} rb_partition;

typedef struct {
    rb_u16 status, count, ebr_count, error_slot;
    rb_u32 error_lba, disk_id;
    rb_u32 ebr_lba[RB_SCAN_EBRS];
    rb_partition entries[RB_SCAN_PARTITIONS];
} rb_partition_scan;

typedef char rb_check_partition[(sizeof(rb_partition) == 20) ? 1 : -1];
typedef char rb_check_scan[(sizeof(rb_partition_scan) == 480) ? 1 : -1];

/* Return zero only after copying exactly one complete 512-byte sector. */
typedef rb_u16 (__cdecl *rb_sector_reader)(rb_u32 lba, rb_u8 *sector, void *opaque);
rb_u16 __cdecl rb_disk_read(rb_u32 lba, rb_u8 *sector, void *opaque);
/* Entries are validated as a complete layout only when status is RB_SCAN_OK. */
rb_u16 rb_scan_partitions(rb_partition_scan *result, rb_sector_reader read,
                         void *opaque, rb_u32 capacity_low, rb_u32 capacity_high,
                         rb_u32 expected_disk_id);
rb_u16 __cdecl rb_scan_selftest(void);

#endif
