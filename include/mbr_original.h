#ifndef RB_MBR_ORIGINAL_H
#define RB_MBR_ORIGINAL_H

#include "mbr_restart.h"

/* The caller establishes first-install custody before any target writes and
   holds exclusive access to the selected, separately identified endpoints.
   Carrier sectors 0 and 1 contain the original header and payload. Sectors
   2 through 5 belong to subsequent publication. The writer checks the
   actual endpoint before writing and returns 512 only after a durable write. */
typedef struct {
    rb_mbr_current_reader current;
    void *disk;
    rb_mbr_restart_reader read;
    rb_u16 (__cdecl *write)(rb_u16 sector, const rb_u8 *bytes,
                            const rb_u8 *expected_endpoint, void *opaque);
    void *carrier;
} rb_mbr_original_io;

/* RB_MBR_OK verifies original revision 1. Repeating on a sealed record
   verifies its exact bytes without writing. No witness or approval is issued. */
rb_u16 rb_mbr_capture_original(const rb_mbr_binding *binding, rb_u16 origin,
                               const rb_mbr_original_io *io);

#endif
