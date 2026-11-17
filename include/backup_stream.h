#ifndef RB_BACKUP_STREAM_H
#define RB_BACKUP_STREAM_H

#include "backup.h"

enum {
    RB_STREAM_OK, RB_STREAM_PARAMS, RB_STREAM_METADATA, RB_STREAM_READ,
    RB_STREAM_CRC, RB_STREAM_CHANGED, RB_STREAM_SINK
};

typedef struct {
    rb_u16 status, detail, kind, index;
    rb_u32 file_sector, sectors;
} rb_backup_stream_result;

typedef char rb_check_backup_stream_result[(sizeof(rb_backup_stream_result) == 16) ? 1 : -1];

typedef rb_u16 (__cdecl *rb_backup_source)(rb_u16 kind, rb_u16 index,
    rb_u32 offset, rb_u8 *sector, void *opaque);
typedef rb_u16 (__cdecl *rb_backup_sink)(rb_u32 file_sector,
    const rb_u8 *sector, void *opaque);

/* Assemble an explicitly described container into a PROVISIONAL destination.
   Source coordinates are role/index/sector-offset, never an implicit disk LBA:
   original and approved MBR bytes must have separate, explicit sources.
   Neither role's provenance, approval, semantics nor live binding is proved.

   Pass one checks all framing and payload CRCs without calling the sink. Pass
   two repeats the checks and emits file-relative sectors 0..file_sectors-1.
   Ordered body/tail fingerprints must also agree. Whole-record CRC equality
   alone does not detect a changed body with a recalculated trailing CRC.

   Callbacks return zero after copying/consuming all 512 bytes, nonzero on error.
   The sector pointer is temporary; callbacks must not retain it or modify the
   metadata/result. Inputs must stay stable and must not overlap the result.
   Source and sink must be independent. All delivered bytes remain provisional
   until return, including the final sector: on ANY error the entire destination
   must be discarded. No rollback or sink commit is performed. Success reports
   sectors=file_sectors; failure clears that claim and preserves diagnostics.
   A failed sink may have consumed its sector before reporting the error.

   Bounded automatic scratch, no retained pointers, allocation or disk/file I/O.
   Success does not prove destination durability or authorize publication or
   restore; independent destination verification is still required. */
rb_u16 rb_backup_stream(rb_backup_stream_result *result,
    const rb_backup *backup, rb_u32 file_sectors, rb_backup_source source,
    void *source_opaque, rb_backup_sink sink, void *sink_opaque);
rb_u16 __cdecl rb_backup_stream_selftest(void);

#endif
