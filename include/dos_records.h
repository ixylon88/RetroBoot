#ifndef RB_DOS_RECORDS_H
#define RB_DOS_RECORDS_H

#include "dos_boot.h"

enum {
    RB_TIMER_OK, RB_TIMER_DISK, RB_TIMER_RECORDS, RB_TIMER_CHANGED,
    RB_TIMER_FULL, RB_TIMER_WRITE, RB_TIMER_READBACK, RB_TIMER_UNCHANGED,
    RB_TRIAL_HISTORY, RB_TRIAL_VBR, RB_TRIAL_GEOMETRY
};

typedef struct {
    rb_u32 allocation[2], lba[2];
    rb_u8 copies[2][512];
    rb_u16 source;
} rb_dos_record_pair;

typedef struct {
    rb_u16 status, saved, seconds, target;
    rb_u32 lba;
} rb_countdown_edit;

/* A trial collects the state pair and the exact VBR. F9 collects the config pair. */
rb_u16 rb_dos_observe(rb_dos_record_pair *pair, const rb_profile_selection *selection,
                      const rb_loader_snapshot *snapshot, rb_handoff_buffer *trial);
rb_u16 rb_dos_config_pair_valid(const rb_u8 *a, const rb_u8 *b, rb_u16 selected);
typedef struct {
    rb_u32 generation, lba, vbr_crc;
    rb_u16 target, armed;
} rb_trial_review;
rb_u16 rb_trial_open(rb_trial_review *review, rb_handoff_buffer *boot, const rb_dos_choice *choice,
                     const rb_loader_snapshot *snapshot);
rb_u16 rb_trial_start(rb_trial_review *review, const rb_handoff_buffer *boot, const rb_dos_choice *choice,
                      const rb_loader_snapshot *snapshot);
void rb_countdown_open(rb_countdown_edit *edit, const rb_dos_choice *choice,
                       const rb_loader_snapshot *snapshot);
void rb_countdown_save(rb_countdown_edit *edit, const rb_dos_choice *choice,
                       const rb_loader_snapshot *snapshot);
rb_u16 __cdecl rb_dos_write_record(rb_u32 lba, const rb_u8 *sector);

#endif
