#include "record_io.h"

void rb_config_load(rb_config_result *r, rb_sector_reader read, void *opaque,
                    rb_u32 low, rb_u32 high, rb_u32 disk_id, rb_u32 admin_lba)
{
    rb_record_files files;
    rb_u16 i;
    rb_record_read(&files, RB_FILES_CONFIG, read, opaque, low, high, disk_id, admin_lba);
    rb_config_select(r, files.records[0], files.records[1], files.status ? 0 : files.mask,
                     &files.scan, &files.admin);
    if (files.status) {
        r->status = files.status; r->detail = files.detail; r->error_lba = files.error_lba;
        r->copies[0] = r->copies[1] = files.status; return;
    }
    if (r->status && r->status != RB_CONFIG_CONFLICT && r->status != RB_CONFIG_MISSING) {
        r->error_lba = files.file_lba[r->copies[0] == r->status ? 0 : 1];
    }
    for (i = 0; i < 2; ++i) {
        if (files.copies[i] == RB_CONFIG_IO) {
            r->copies[i] = RB_CONFIG_IO; r->error_lba = files.error_lba;
            if (r->source == RB_CONFIG_NONE) { r->status = RB_CONFIG_IO; }
        }
    }
}
