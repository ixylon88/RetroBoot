#ifndef RB_BACKUP_FORMAT_H
#define RB_BACKUP_FORMAT_H

#include "backup.h"

/* Internal framing rules shared by the decoder and metadata encoder.
   The entry check requires an accepted identity/count/file-size check first. */
rb_u16 rb_backup_identity(const rb_backup *backup, rb_u32 file_sectors);
rb_u16 rb_backup_entries(const rb_backup *backup, rb_u32 file_sectors);
/* Unfinalized accumulator; a payload may exceed the 64 KiB segment. */
rb_u32 rb_backup_crc_update(rb_u32 crc, const rb_u8 *bytes, rb_u16 length);

#endif
