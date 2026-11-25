#ifndef RB_DOS_COUNTDOWN_H
#define RB_DOS_COUNTDOWN_H

#include "dos_boot.h"

enum {
    RB_TIMER_OK, RB_TIMER_DISK, RB_TIMER_RECORDS, RB_TIMER_CHANGED,
    RB_TIMER_FULL, RB_TIMER_WRITE, RB_TIMER_READBACK, RB_TIMER_UNCHANGED
};

typedef struct {
    rb_u32 allocation[2], lba[2];
    rb_u8 copies[2][512];
    rb_u16 source;
} rb_countdown_pair;

typedef struct {
    rb_u16 status, saved, seconds, target;
    rb_u32 lba;
} rb_countdown_edit;

rb_u16 rb_countdown_observe(rb_countdown_pair *pair, const rb_dos_choice *choice,
                            const rb_loader_snapshot *snapshot);
void rb_countdown_open(rb_countdown_edit *edit, const rb_dos_choice *choice,
                       const rb_loader_snapshot *snapshot);
void rb_countdown_save(rb_countdown_edit *edit, const rb_dos_choice *choice,
                       const rb_loader_snapshot *snapshot);
rb_u16 __cdecl rb_dos_write_config(rb_u32 lba, const rb_u8 *sector);

#endif
