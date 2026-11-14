#ifndef RB_RESCUE_MATCH_H
#define RB_RESCUE_MATCH_H

#include "backup_target.h"

enum { RB_RMATCH_OK, RB_RMATCH_FILE, RB_RMATCH_SAVED, RB_RMATCH_PROBE,
       RB_RMATCH_TARGET, RB_RMATCH_CHANGED };

typedef struct {
    rb_u16 status, detail, nested, record_detail;
    rb_u32 file_lba, disk_lba;
    rb_rescue_device device;
    rb_backup_target observed;
} rb_rescue_match;

/* Fresh synchronous file validation and BIOS discovery on every call.
   Read-only metadata correspondence, never restore/boot authorization.
   Failed operations retain diagnostics only; private scratch is non-reentrant. */
void rb_rescue_backup_match(rb_u16 boot, rb_rescue_match *result);

#endif
