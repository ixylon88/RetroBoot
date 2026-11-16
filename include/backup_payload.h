#ifndef RB_BACKUP_PAYLOAD_H
#define RB_BACKUP_PAYLOAD_H

#include "backup_plan.h"

typedef struct {
    rb_backup_plan plan;
    rb_u32 crc[RB_CAPTURE_MAX];
} rb_backup_payloads;

typedef char rb_check_backup_payloads[(sizeof(rb_backup_payloads) == 1072) ? 1 : -1];

/* Fresh planning and complete boot checks in each of two passes, followed by
   streaming every live extent and calculating its ordinary whole-extent CRC32.
   Every read also enters the planner's separate body/tail fingerprints. CRCs
   alone cannot detect a changed record with a recalculated trailing CRC.

   crc[i] describes plan.entries[i]; unused CRC slots are zero. Failure clears
   all plan claims and CRCs, retaining only the plan's diagnostic fields.
   Only bounded sector scratch is used; payload bytes are not retained. No file
   offsets, original-MBR source, MBR approval, export or write grant is produced.
   The result must be writable and must not overlap inputs. The planner's fresh
   device, stable-source and non-reentrant preconditions still apply. */
void rb_backup_payload_capture(rb_backup_payloads *result,
    const rb_rescue_device *device, rb_sector_reader read, void *opaque);
rb_u16 __cdecl rb_backup_payload_selftest(void);

#endif
