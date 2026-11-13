#ifndef RB_RESCUE_H
#define RB_RESCUE_H

#include "partitions.h"

enum { RB_RESCUE_OK, RB_RESCUE_NO_DISK, RB_RESCUE_PARAMS,
       RB_RESCUE_GEOMETRY, RB_RESCUE_IO, RB_RESCUE_CHANGED };

typedef struct {
    rb_u16 drive, mode, heads, sectors_per_track;
    rb_u32 capacity_low, capacity_high;
} rb_rescue_device;

typedef struct {
    rb_u16 status, layout, entries, ebrs, signature, marker;
    rb_u32 disk_id, mbr_crc, error_lba;
} rb_rescue_result;

typedef char rb_rescue_device_size[(sizeof(rb_rescue_device) == 16) ? 1 : -1];

/* Fresh BIOS discovery of drive 80h; no dependence on an HDD boot context.
 * Failure clears both the result and the low-memory reader context. */
rb_u16 __cdecl rb_rescue_probe(rb_rescue_device *device);
/* Diagnostic only: the observed disk ID is not an independent media identity.
 * Read MBR/EBRs and recheck the full MBR; never read a target VBR or file. */
void rb_rescue_inspect(rb_rescue_result *result, const rb_rescue_device *device,
                       rb_sector_reader read, void *opaque);
rb_u16 __cdecl rb_rescue_runtime(void);
void __cdecl rb_rescue_run(rb_u16 boot_drive);
rb_u16 __cdecl rb_rescue_selftest(void);

#endif
