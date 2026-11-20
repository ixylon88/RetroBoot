#ifndef RB_MBR_REVIEW_UI_H
#define RB_MBR_REVIEW_UI_H
#include "mbr_restart.h"

typedef struct {
    const rb_mbr_binding *binding;
    const rb_u8 *witness_id;
    rb_mbr_current_reader read;
    void *disk;
    int (__cdecl *matches)(void *disk); /* physical identity check before publication */
    rb_mbr_restart_reader carrier_read;
    rb_u16 (__cdecl *carrier_write)(rb_u16 n, const rb_u8 *bytes, const rb_u8 *id, void *disk);
    /* Raw trusted ATA profile; null for the controlled labelled fixture. */
    const rb_u8 *ata_profile;
} rb_mbr_review_source;

rb_u16 rb_mbr_review_key(void);
rb_u16 rb_mbr_review_action(rb_u16 key, rb_u16 boot_drive, const rb_mbr_review_source *source);
#endif
