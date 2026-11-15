#ifndef RB_BACKUP_SAVED_H
#define RB_BACKUP_SAVED_H

#include "backup_records.h"

/* Internal handoff to subsequent saved-content checks. The context is valid
   only after a successful open and until the next record check. No live I/O.
   Record-sector scratch is dead after open; the boot checker may overwrite
   it. Container, scan, selected records and reader remain live outside it. */
typedef struct {
    rb_backup container;
    rb_partition_scan scan;
    rb_config_result config;
    rb_state_result state;
    rb_sector_reader read;
    void *opaque;
    union {
        struct { rb_u8 mbr[512], a[512], b[512]; } records;
        struct { rb_u8 sector[512], first[512], continuation[512]; } boot;
    } scratch;
    rb_u16 read_status, kind, index;
    rb_u32 lba;
} rb_backup_saved;

rb_backup_saved *rb_backup_open_records(rb_backup_records *result,
    rb_sector_reader read, void *opaque, rb_u32 file_sectors);

#endif
