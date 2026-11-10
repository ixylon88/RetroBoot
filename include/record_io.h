#ifndef RB_RECORD_IO_H
#define RB_RECORD_IO_H

#include "config.h"

enum { RB_FILES_CONFIG, RB_FILES_STATE };

typedef struct {
    rb_partition_scan scan;
    rb_partition admin;
    rb_u8 records[2][512];
    rb_u32 error_lba, file_lba[2];
    rb_u16 status, detail, mask, copies[2];
} rb_record_files;

/* Returns RB_CONFIG_* codes for the common single-cluster file boundary.
 * Both requested files are freshly resolved; all four known file names are
 * checked for duplicate names and shared starting clusters. */
void rb_record_read(rb_record_files *result, rb_u16 family,
                    rb_sector_reader read, void *opaque, rb_u32 low, rb_u32 high,
                    rb_u32 disk_id, rb_u32 admin_lba);

#endif
