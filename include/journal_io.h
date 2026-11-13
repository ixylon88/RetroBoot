#ifndef RB_JOURNAL_IO_H
#define RB_JOURNAL_IO_H

#include "journal.h"

enum {
    RB_JLOAD_OK, RB_JLOAD_ALLOCATION, RB_JLOAD_CONFIG, RB_JLOAD_STATE,
    RB_JLOAD_IDENTITY, RB_JLOAD_IO, RB_JLOAD_CHANGED
};

typedef struct {
    rb_journal_result journal;
    rb_u32 error_lba;
    rb_u16 status, detail;
} rb_journal_diagnosis;

/* Fresh, read-only observation: eight-file allocation audit, four identity
 * records, six mapped journal sectors and a final current-MBR comparison.
 * No target VBR, disk write or boot action. Private scratch is non-reentrant
 * and cleared before/after each call; no pointers or sector map survive. */
void rb_journal_load(rb_journal_diagnosis *result, rb_sector_reader read, void *opaque,
                     rb_u32 low, rb_u32 high, rb_u32 disk_id, rb_u32 admin_lba,
                     rb_u16 io_mode, rb_u16 heads, rb_u16 sectors_per_track);

#endif
