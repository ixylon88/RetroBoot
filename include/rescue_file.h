#ifndef RB_RESCUE_FILE_H
#define RB_RESCUE_FILE_H

#include "backup_boot.h"

#define RB_FLOPPY_SECTORS 2880U
#define RB_FILE_MAX 2048U
#define RB_FILE_LAST_CLUSTER 2848U
#define RB_FILE_FAT_BYTES (9U * 512U)
#define RB_FILE_INDEX_STRIDE 16U
#define RB_FILE_INDEX_COUNT ((RB_FILE_MAX + RB_FILE_INDEX_STRIDE - 1) / RB_FILE_INDEX_STRIDE)
enum { RB_FILE_OK, RB_FILE_IO, RB_FILE_BPB, RB_FILE_FATS, RB_FILE_DIRECTORY,
       RB_FILE_MISSING, RB_FILE_DUPLICATE, RB_FILE_SIZE, RB_FILE_CHAIN,
       RB_FILE_CROSSLINK, RB_FILE_CHANGED, RB_FILE_RANGE };

typedef struct {
    rb_u8 links[RB_FILE_FAT_BYTES - RB_FILE_INDEX_COUNT * sizeof(rb_u16)];
    /* After both FAT copies compare equal, the unused tail holds the first
       cluster of each group of logical file sectors. */
    rb_u16 first_cluster[RB_FILE_INDEX_COUNT];
} rb_rescue_file_map;

typedef char rb_check_rescue_file_map[
    (sizeof(rb_rescue_file_map) == RB_FILE_FAT_BYTES
     && RB_FILE_LAST_CLUSTER + RB_FILE_LAST_CLUSTER / 2 + 2
        <= sizeof(((rb_rescue_file_map *)0)->links)) ? 1 : -1];

typedef struct {
    rb_sector_reader read;
    void *opaque;
    rb_u32 metadata_crc, error_lba;
    rb_u16 status, ready, sectors;
    rb_rescue_file_map map;
} rb_rescue_file;

/* Restricted 1440 KiB FAT12 superfloppy, flat root, exact RBBACKUP.RBB name.
   Every root file chain is checked before any file payload read. Failure
   invalidates the complete map. No writer and no general filesystem mount. */
void rb_rescue_file_open(rb_rescue_file *file, rb_sector_reader read, void *opaque);
void rb_rescue_file_open_named(rb_rescue_file *file, rb_sector_reader read, void *opaque, const char *name);
rb_u16 rb_rescue_file_lba(const rb_rescue_file *file, rb_u16 offset);
/* Validate the read-only profile and the five-sector RBWITNES.BIN extent. */
int rb_rescue_witness_extent(rb_rescue_file *file, rb_sector_reader read, void *opaque,
                             rb_u16 lba, int writable);
rb_u16 __cdecl rb_rescue_file_read(rb_u32 sector, rb_u8 *out, void *file);
rb_u16 rb_rescue_file_recheck(rb_rescue_file *file);
rb_u16 __cdecl rb_floppy_read(rb_u32 lba, rb_u8 *out, void *boot_drive);
void rb_rescue_backup_check(rb_u16 boot, rb_u16 *file_status, rb_u32 *file_lba,
                            rb_backup_boot *result);

#endif
