#ifndef RB_BACKUP_TARGET_H
#define RB_BACKUP_TARGET_H

#include "backup.h"
#include "rescue.h"

enum {
    RB_BTARGET_OK, RB_BTARGET_PARAMS, RB_BTARGET_IO, RB_BTARGET_ALLOCATION,
    RB_BTARGET_CONFIG, RB_BTARGET_STATE, RB_BTARGET_IDENTITY,
    RB_BTARGET_CAPACITY, RB_BTARGET_GEOMETRY, RB_BTARGET_LAYOUT,
    RB_BTARGET_CHANGED, RB_BTARGET_INSTALLATION
};

typedef struct {
    rb_u16 status, detail;
    rb_u32 error_lba, disk_id, layout_crc, admin_start, admin_sectors;
    rb_u8 media_id[16];
    rb_u32 config_generation, state_generation;
} rb_backup_target;

typedef char rb_check_backup_target[(sizeof(rb_backup_target) == 48) ? 1 : -1];

typedef struct {
    rb_u32 start, vbr_crc;
    rb_u16 index; /* Index in the selected, validated installation state. */
} rb_backup_ready;

typedef struct {
    rb_partition_scan scan;
    rb_u32 record_lba[4]; /* Config A/B, state A/B, from the audited allocation. */
    rb_u32 journal_lba[2][3]; /* Complete physical maps from the same audit. */
    rb_backup_ready ready[4];
    rb_u16 ready_count;
} rb_backup_sources;

/* Independent observation, without saved identity claims. Performs the same
   two acquisitions as the comparison below. Optional sources are published
   only on success and cleared on failure, including selected READY VBR claims.
   Selected profile installation references must resolve to compatible selected
   state entries; approved profiles require READY. Status INSTALLATION reports
   the first profile index in detail and its target start in error_lba.
   Result, sources and inputs must not
   overlap; result is required. No boot-area contents or MBR provenance check. */
void rb_backup_observe_target(rb_backup_target *result, rb_backup_sources *sources,
    const rb_rescue_device *device, rb_sector_reader read, void *opaque);

/* Read-only comparison with a freshly discovered BIOS device. All disk addresses
   come from live MBR/EBR/FAT metadata, never from the backup's extent list.
   The caller must validate the complete saved file separately. This API checks
   its identity/geometry claims against two live metadata acquisitions, including
   consistency of selected live configuration/state installation references.
   Matching copied identifiers cannot distinguish a cloned disk. Success is
   neither a complete backup check, a physical-device identity nor restore or
   boot authority. Stable sources and a non-reentrant call are required;
   only status/detail/error_lba survive failure. No BIOS discovery is performed. */
void rb_backup_match_target(rb_backup_target *result, const rb_backup *backup,
    const rb_rescue_device *device, rb_sector_reader read, void *opaque);
/* Returns the audited source maps only on a full saved/live match. */
void rb_backup_match_sources(rb_backup_target *result, rb_backup_sources *sources, const rb_backup *backup,
    const rb_rescue_device *device, rb_sector_reader read, void *opaque);
rb_u16 __cdecl rb_backup_target_selftest(void);

#endif
