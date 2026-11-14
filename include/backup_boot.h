#ifndef RB_BACKUP_BOOT_H
#define RB_BACKUP_BOOT_H

#include "backup_records.h"

enum {
    RB_BBOOT_OK, RB_BBOOT_RECORDS, RB_BBOOT_IO, RB_BBOOT_CHANGED,
    RB_BBOOT_VOLUME, RB_BBOOT_COVERAGE, RB_BBOOT_FAT32_LAYOUT,
    RB_BBOOT_FSINFO, RB_BBOOT_COPY, RB_BBOOT_READY
};

typedef struct {
    rb_u16 status, detail, record_detail, kind, index;
    rb_u32 error_lba;
    rb_u16 volumes, fat16, fat32, reserved_sectors, ready_matches;
} rb_backup_boot;

typedef char rb_check_backup_boot[(sizeof(rb_backup_boot) == 24) ? 1 : -1];

/* Stable, FILE-relative reader; non-reentrant. Validates saved records first,
   then complete FAT16/FAT32 reserved areas. FAT32 support requires FSInfo at 1
   and a three-sector boot record, with an optional non-overlapping backup.
   No live-media match, filesystem/data backup, executable-code proof or restore
   authority. Only diagnostics survive failure. */
void rb_backup_check_boot(rb_backup_boot *result, rb_sector_reader read,
    void *opaque, rb_u32 file_sectors);
rb_u16 __cdecl rb_backup_boot_selftest(void);

#endif
