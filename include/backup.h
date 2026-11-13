#ifndef RB_BACKUP_H
#define RB_BACKUP_H

#include "partitions.h"

#define RB_BACKUP_MAX 42U
#define RB_BACKUP_SECTORS 2048UL

enum {
    RB_BACKUP_OK, RB_BACKUP_IO, RB_BACKUP_FORMAT, RB_BACKUP_CRC,
    RB_BACKUP_RANGE, RB_BACKUP_ORDER, RB_BACKUP_OVERLAP, RB_BACKUP_MISSING
};
enum {
    RB_BACKUP_ORIGINAL = 1, RB_BACKUP_APPROVED, RB_BACKUP_EBR,
    RB_BACKUP_BOOT, RB_BACKUP_CONFIG_A, RB_BACKUP_CONFIG_B,
    RB_BACKUP_STATE_A, RB_BACKUP_STATE_B
};

typedef struct {
    rb_u16 kind, index;
    rb_u32 lba, sectors, file_sector, crc, owner_start, owner_sectors;
} rb_backup_extent;

typedef struct {
    rb_u32 generation, disk_id, layout_crc, admin_start, admin_sectors;
    rb_u32 capacity_low, capacity_high;
    rb_u16 count, route, heads, sectors_per_track;
    rb_u8 media_id[16];
    rb_backup_extent entries[RB_BACKUP_MAX];
} rb_backup;

typedef char rb_check_backup_extent[(sizeof(rb_backup_extent) == 28) ? 1 : -1];

/* Container integrity only: no live identity, content semantics or write grant.
   Reader addresses are FILE-relative 512-byte sectors, never HDD LBAs.
   The source must remain stable during this call. Private scratch makes this
   non-reentrant. Every failure clears the entire result, including entries. */
rb_u16 rb_backup_validate(rb_backup *result, rb_sector_reader read,
                          void *opaque, rb_u32 file_sectors);
rb_u16 __cdecl rb_backup_selftest(void);

#endif
