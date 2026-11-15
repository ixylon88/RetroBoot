#ifndef RB_BACKUP_ENCODE_H
#define RB_BACKUP_ENCODE_H

#include "backup.h"

/* Encode one FILE-relative metadata sector: 0 header, 1..4 descriptor table.
   Checks the complete framing on every call; returns existing RB_BACKUP codes.
   All 512 output bytes are cleared on failure (unless output is null).
   Required output must not overlap input. No static scratch or retained state.

   The caller explicitly supplies all roles, addresses, file offsets, payload
   CRCs and identity claims. Payload bytes/CRCs, record semantics, live binding,
   original-MBR provenance and current-MBR approval are NOT established here.
   Kind zero from a preliminary capture plan is rejected, never promoted to an
   original/approved MBR. This API neither reads nor writes any disk or file. */
rb_u16 rb_backup_encode_metadata(const rb_backup *backup, rb_u32 file_sectors,
    rb_u16 metadata_sector, rb_u8 *output);
rb_u16 __cdecl rb_backup_encode_selftest(void);

#endif
