#include "rescue_file.h"

static rb_rescue_file file;

void rb_rescue_backup_check(rb_u16 boot, rb_u16 *status, rb_u32 *lba, rb_backup_boot *result)
{
    rb_u16 i;
    for (i = 0; i < sizeof(*result); ++i) { ((rb_u8 *)result)[i] = 0; }
    rb_rescue_file_open(&file, rb_floppy_read, &boot);
    if (!file.status) {
        rb_backup_check_boot(result, rb_rescue_file_read, &file, file.sectors);
        if (!file.status && !result->status) { rb_rescue_file_recheck(&file); }
    }
    *status = file.status; *lba = file.error_lba;
    if (file.status) {
        for (i = 0; i < sizeof(*result); ++i) { ((rb_u8 *)result)[i] = 0; }
    }
    /* The caller's boot-drive pointer is valid only during this operation. */
    file.ready = 0; file.read = (rb_sector_reader)0; file.opaque = (void *)0;
}
