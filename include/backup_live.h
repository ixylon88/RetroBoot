#ifndef RB_BACKUP_LIVE_H
#define RB_BACKUP_LIVE_H

#include "backup_payload.h"
#include "backup_stream.h"

enum {
    RB_LIVE_OK, RB_LIVE_PARAMS, RB_LIVE_METADATA, RB_LIVE_CAPTURE,
    RB_LIVE_IDENTITY, RB_LIVE_EXTENT, RB_LIVE_STREAM, RB_LIVE_CHANGED
};

typedef struct {
    rb_u16 status, detail;
    rb_u16 capture_status, capture_detail, capture_nested, capture_index;
    rb_u32 error_lba;
    rb_backup_stream_result stream;
} rb_backup_live_result;

typedef char rb_check_backup_live_result[(sizeof(rb_backup_live_result) == 32) ? 1 : -1];

/* Bind one provisional stream to fresh live observations, without retaining a
   reusable source map. Both MBR roles use the explicit mbr_source callback;
   the live current MBR is never promoted to either role. Their provenance,
   approval and saved-content semantics remain the caller's separate work.

   A fresh payload capture must match the supplied identity and every non-MBR
   extent, including its CRC. Physical reads use only that independently built
   plan. The stream's two passes are followed by another full capture. Ordered
   fingerprints/counts of both captures must agree, including resealed records.

   The device description must be freshly discovered and all inputs/sources
   stable throughout this non-reentrant call. No BIOS discovery, atomic source
   snapshot, authentication, destination persistence or write grant is supplied.
   As with the underlying capture/stream APIs, repeated reads cannot detect
   every coordinated transient change or CRC collision. Source/sink contexts
   must be independent; inputs, result and callback buffers must not overlap.

   All sink bytes remain provisional until this wrapper returns successfully.
   ANY failure, including the closing capture after the final sink call, clears
   stream.sectors and requires discarding ALL output. Stream diagnostics are
   valid for RB_LIVE_STREAM; capture diagnostics are valid for RB_LIVE_CAPTURE.
   Other errors use detail (metadata code, identity field or descriptor index).
   Null result returns PARAMS without touching memory or invoking callbacks. */
rb_u16 rb_backup_live_stream(rb_backup_live_result *result,
    const rb_backup *backup, rb_u32 file_sectors,
    const rb_rescue_device *device, rb_sector_reader read, void *disk_opaque,
    rb_backup_source mbr_source, void *mbr_opaque,
    rb_backup_sink sink, void *sink_opaque);
rb_u16 __cdecl rb_backup_live_selftest(void);

#endif
