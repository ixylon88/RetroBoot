#ifndef RB_BACKUP_PLAN_H
#define RB_BACKUP_PLAN_H

#include "backup_target.h"

/* One descriptor remains reserved for a separately sourced original MBR.
   Kind zero is deliberately NOT an on-disk backup-container kind. */
#define RB_CAPTURE_MAX (RB_BACKUP_MAX - 1U)
#define RB_CAPTURE_CURRENT_MBR 0U

enum {
    RB_CAPTURE_OK, RB_CAPTURE_PARAMS, RB_CAPTURE_TARGET, RB_CAPTURE_VOLUME,
    RB_CAPTURE_FAT32_LAYOUT, RB_CAPTURE_LIMIT, RB_CAPTURE_CHANGED,
    RB_CAPTURE_IO, RB_CAPTURE_RANGE, RB_CAPTURE_BOOT
};

typedef struct {
    rb_u16 kind, index;
    rb_u32 lba, sectors, owner_start, owner_sectors;
} rb_capture_extent;

typedef struct {
    rb_u16 status, detail, nested, index;
    rb_u32 error_lba;
    rb_backup_target observed;
    rb_rescue_device device;
    rb_u16 count, volumes;
    rb_u32 live_sectors, estimated_container_sectors;
    rb_capture_extent entries[RB_CAPTURE_MAX];
} rb_backup_plan;

typedef char rb_check_capture_extent[(sizeof(rb_capture_extent) == 20) ? 1 : -1];
typedef char rb_check_backup_plan[(sizeof(rb_backup_plan) == 908) ? 1 : -1];

/* Preliminary read plan, not a complete backup or any write/boot permission.
   Two passes compare audited live metadata and complete supported FAT reserved
   areas, including FSInfo, backup copies and selected READY first-VBR claims.
   Estimated size includes five container sectors and one original-MBR sector;
   original-MBR provenance and approval of the current MBR remain unresolved.
   No payloads, payload CRCs, file offsets or generation are produced.
   Required writable result must not overlap inputs. Stable sources and a fresh
   device description are caller preconditions. Private scratch is non-reentrant.
   Failure clears every field except status/detail/nested/index/error_lba. */
void rb_backup_plan_capture(rb_backup_plan *result, const rb_rescue_device *device,
    rb_sector_reader read, void *opaque);
rb_u16 __cdecl rb_backup_plan_selftest(void);

#endif
