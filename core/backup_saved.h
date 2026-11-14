#ifndef RB_BACKUP_SAVED_H
#define RB_BACKUP_SAVED_H

#include "backup_records.h"

/* Internal handoff to subsequent saved-content checks. The context is valid
   only after a successful open and until the next record check. No live I/O. */
typedef struct {
    rb_backup container;
    rb_partition_scan scan;
    rb_config_result config;
    rb_state_result state;
    rb_sector_reader read;
    void *opaque;
    rb_u8 mbr[512], a[512], b[512];
    rb_u16 read_status, kind, index;
    rb_u32 lba;
} rb_backup_saved;

const rb_backup_saved *rb_backup_open_records(rb_backup_records *result,
    rb_sector_reader read, void *opaque, rb_u32 file_sectors);

#endif
