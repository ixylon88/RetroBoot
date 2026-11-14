#ifndef RB_RESCUE_FILE_H
#define RB_RESCUE_FILE_H

#include "backup_boot.h"

#define RB_FLOPPY_SECTORS 2880U
#define RB_FILE_MAX 2048U
enum { RB_FILE_OK, RB_FILE_IO, RB_FILE_BPB, RB_FILE_FATS, RB_FILE_DIRECTORY,
       RB_FILE_MISSING, RB_FILE_DUPLICATE, RB_FILE_SIZE, RB_FILE_CHAIN,
       RB_FILE_CROSSLINK, RB_FILE_CHANGED, RB_FILE_RANGE };

typedef struct {
    rb_sector_reader read;
    void *opaque;
    rb_u32 metadata_crc, error_lba;
    rb_u16 status, ready, sectors, chain[RB_FILE_MAX];
} rb_rescue_file;

/* Restricted 1440 KiB FAT12 superfloppy, flat root, exact RBBACKUP.RBB name.
   Every root file chain is checked before any file payload read. Failure
   invalidates the complete map. No writer and no general filesystem mount. */
void rb_rescue_file_open(rb_rescue_file *file, rb_sector_reader read, void *opaque);
rb_u16 __cdecl rb_rescue_file_read(rb_u32 sector, rb_u8 *out, void *file);
rb_u16 rb_rescue_file_recheck(rb_rescue_file *file);
rb_u16 __cdecl rb_floppy_read(rb_u32 lba, rb_u8 *out, void *boot_drive);
void rb_rescue_backup_check(rb_u16 boot, rb_u16 *file_status, rb_u32 *file_lba,
                            rb_backup_boot *result);

#endif
