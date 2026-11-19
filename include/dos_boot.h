#ifndef RB_DOS_BOOT_H
#define RB_DOS_BOOT_H

#include "bios_ui.h"
#include "journal_io.h"
#include "profile_boot.h"

typedef struct {
    rb_profile_selection selected;
    rb_u16 countdown;
} rb_dos_choice;

enum { RB_DOS_JOURNAL = RB_PROFILE_CODE + 1, RB_DOS_GEOMETRY };

void __cdecl rb_dos_geometry(rb_u16 *geometry);
void __cdecl rb_video_console(void);

void rb_dos_open(rb_dos_choice *choice, rb_config_result *config, const rb_loader_snapshot *snapshot);
rb_u16 rb_dos_start(const rb_dos_choice *choice, rb_u16 automatic,
                    rb_config_result *config, rb_state_result *state, rb_visibility_result *visibility,
                    rb_journal_diagnosis *journal, const rb_loader_snapshot *snapshot);

#endif
