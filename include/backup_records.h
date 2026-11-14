#ifndef RB_BACKUP_RECORDS_H
#define RB_BACKUP_RECORDS_H

#include "backup.h"
#include "state.h"

enum {
    RB_BREC_OK, RB_BREC_CONTAINER, RB_BREC_IO, RB_BREC_CHANGED,
    RB_BREC_LAYOUT, RB_BREC_COVERAGE, RB_BREC_ADMIN, RB_BREC_CONFIG,
    RB_BREC_STATE, RB_BREC_IDENTITY, RB_BREC_INSTALLATION
};
enum {
    RB_BREC_MISSING_EBR = 1, RB_BREC_EBR_SET, RB_BREC_BOOT_OWNER,
    RB_BREC_MISSING_START
};

typedef struct {
    rb_u16 status, detail, kind, index;
    rb_u32 error_lba;
    rb_u16 partitions, ebrs, boot_areas, config_source, state_source;
    rb_u32 config_generation, state_generation;
} rb_backup_records;

typedef char rb_check_backup_records[(sizeof(rb_backup_records) == 30) ? 1 : -1];

/* File-relative, stable-source reader. Checks approved-view partition and
   record consistency after container validation; no live disk access, saved
   filesystem completeness, original-MBR provenance or restore authority.
   Private scratch is non-reentrant. Only diagnostics survive failure. */
void rb_backup_check_records(rb_backup_records *result, rb_sector_reader read,
                              void *opaque, rb_u32 file_sectors);
rb_u16 __cdecl rb_backup_records_selftest(void);

#endif
