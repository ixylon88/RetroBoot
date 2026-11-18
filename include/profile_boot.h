#ifndef RB_PROFILE_BOOT_H
#define RB_PROFILE_BOOT_H

#include "handoff.h"
#include "visibility.h"

enum {
    RB_PROFILE_OK, RB_PROFILE_SELECTION, RB_PROFILE_PROOF,
    RB_PROFILE_CHANGE, RB_PROFILE_TARGET, RB_PROFILE_CODE
};

typedef struct {
    rb_u16 valid;
    rb_u32 disk_id, layout_crc;
    rb_u8 media_id[16];
    rb_profile entry;
} rb_profile_selection;

/* Selection survives record reordering by Entry ID, never by array position.
 * A changed displayed name, target, installation identity or policy requires
 * a new review. Independent generation changes alone do not change selection. */
void rb_profile_remember(rb_profile_selection *selection, const rb_config_result *config, rb_u16 index);
rb_u16 rb_profile_reselect(const rb_profile_selection *selection, const rb_config_result *config, rb_u16 *index);

/* Stage only the exact VBR read by a fresh READY, approved installation and
 * matching visibility proof. No OS-sector reread or partition writes. */
rb_u16 rb_stage_profile(rb_handoff_buffer *result, rb_visibility_result *visibility,
                        const rb_config_result *config, const rb_state_result *state,
                        rb_u16 index, rb_sector_reader read, void *opaque,
                        rb_u32 low, rb_u32 high, rb_u32 admin_lba);

#endif
