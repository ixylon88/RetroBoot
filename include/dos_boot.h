#ifndef RB_DOS_BOOT_H
#define RB_DOS_BOOT_H

#include "bios_ui.h"
#include "journal_io.h"
#include "profile_boot.h"

/* Three primary OS slots can coexist with the extended management container. */
#define RB_DOS_PROFILES 3U
typedef struct {
    /* The single-profile recovery review uses profiles[0] while count is zero. */
    rb_profile_selection profiles[RB_DOS_PROFILES];
    rb_u16 count, default_index, countdown, trial;
    rb_state_proof records;
} rb_dos_choice;

enum { RB_DOS_JOURNAL = RB_PROFILE_CODE + 1, RB_DOS_GEOMETRY };

void __cdecl rb_dos_geometry(rb_u16 *geometry);
void __cdecl rb_video_console(void);
rb_u16 rb_dos_geometry_matches(const rb_profile *entry, const rb_u8 *sector);

void rb_dos_open(rb_dos_choice *choice, rb_config_result *config,
                 rb_state_result *state, const rb_loader_snapshot *snapshot);
rb_u16 rb_dos_start(const rb_dos_choice *choice, rb_u16 selection, rb_u16 automatic, rb_u16 *index,
                    rb_config_result *config, rb_state_result *state, rb_visibility_result *visibility,
                    rb_journal_diagnosis *journal, const rb_loader_snapshot *snapshot);

#endif
