#ifndef RB_BACKUP_VERIFY_H
#define RB_BACKUP_VERIFY_H

#include "backup_live.h"
#include "mbr_restart.h"

typedef struct {
    const rb_mbr_binding *binding;
    const rb_u8 *witness_id;
    rb_mbr_restart_source witness, carrier;
} rb_backup_history;

typedef struct {
    rb_rescue_device device;
    rb_sector_reader read;
    /* Identify the same physical disk addressed by read, under exclusive access. */
    rb_u16 (__cdecl *identify)(rb_mbr_target *actual, void *opaque);
    void *opaque;
} rb_backup_input;

typedef struct {
    rb_backup_sink write;
    /* Reopen the staged bytes read-only and report the actual byte length.
       A subsequent reopen checks the same immutable destination again. */
    rb_u16 (__cdecl *reopen)(rb_u32 *bytes, void *opaque);
    rb_sector_reader read;
    void *opaque;
} rb_backup_destination;

enum {
    RB_VERIFY_OK, RB_VERIFY_PARAMS, RB_VERIFY_TARGET, RB_VERIFY_WITNESS,
    RB_VERIFY_CARRIER, RB_VERIFY_APPROVAL, RB_VERIFY_PRODUCER, RB_VERIFY_OPEN,
    RB_VERIFY_LENGTH, RB_VERIFY_SAVED, RB_VERIFY_READ, RB_VERIFY_DIFFER,
    RB_VERIFY_REPLAY, RB_VERIFY_CHANGED
};

typedef struct {
    rb_u16 status, detail, nested, record_detail;
    rb_u32 error_sector, sectors, approved_revision;
} rb_backup_verified;

/* Produce a fresh provisional stream, then independently reopen its actual
   destination. Inputs, live disk, witness, carrier and destination are distinct
   stable sources under exclusive access. The plan is copied before any saved
   reader can reuse its scratch. All callbacks except MBR history
   readers return zero on success. No direct device writes or publication.
   Discard ALL delivered bytes on failure, even after the last write or read.
   Non-reentrant. Only a final success sets sectors and approved_revision. */
rb_u16 rb_backup_verify_live(rb_backup_verified *result, const rb_backup *claims,
    rb_u32 file_sectors, const rb_backup_input *source,
    const rb_backup_history *history, const rb_backup_destination *destination);

#endif
