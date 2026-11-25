#ifndef RB_DOS_SWITCH_H
#define RB_DOS_SWITCH_H

#include "dos_boot.h"

enum { RB_SWITCH_OK, RB_SWITCH_CHANGED, RB_SWITCH_FULL, RB_SWITCH_IO };

/* Borrowed until the next journal load. Intermediate journal sectors are
 * accessible only after a complete, successful allocation and physical read. */
typedef struct {
    rb_journal_diagnosis diagnosis;
    rb_u32 ownership[2], admin_lba;
    rb_u32 (*lba)[3];
    rb_u8 (*slots)[RB_JOURNAL_BYTES];
    const rb_u8 *mbr;
    const rb_config_result *config;
    const rb_state_result *state;
} rb_switch_disk;

typedef struct {
    rb_u32 ownership[2], lba[2][3], sequence;
    rb_u16 prepare, armed;
} rb_switch_review;

rb_u16 rb_switch_read(rb_switch_disk *disk, const rb_loader_snapshot *snapshot);
rb_u16 rb_switch_open(rb_switch_review *review, const rb_dos_choice *choice, rb_u16 selection,
                      const rb_loader_snapshot *snapshot, const rb_visibility_result *shown);
rb_u16 rb_switch_apply(rb_switch_review *review, const rb_dos_choice *choice, rb_u16 selection,
                       const rb_loader_snapshot *snapshot, const rb_visibility_result *shown);
rb_u16 __cdecl rb_dos_write_mbr(const rb_u8 *sector);

#endif
