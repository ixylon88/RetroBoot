#include "profile_test.h"
#include "stage2.h"

rb_u16 __cdecl rb_run_profile_test(rb_config_result *config, rb_state_result *state,
                                   rb_visibility_result *visibility, rb_u16 *index,
                                   rb_u32 disk_id, rb_u32 admin_lba)
{
    rb_profile_selection selected;
    rb_handoff_buffer prepared;
    rb_u16 i;
    rb_u8 *bytes = (rb_u8 *)visibility;

    rb_profile_remember(&selected, config, *index);
    for (i = 0; i < sizeof(*visibility); ++i) { bytes[i] = 0; }

    /* Reuse the menu's record buffers so the C16 stack keeps its 8 KiB budget.
     * Both families are reread even if a prior diagnostic looked successful. */
    rb_config_load(config, rb_disk_read, (void *)0,
        rb_boot.reachable_sectors_low, rb_boot.reachable_sectors_high, disk_id, admin_lba);
    rb_state_load(state, rb_disk_read, (void *)0,
        rb_boot.reachable_sectors_low, rb_boot.reachable_sectors_high, disk_id, admin_lba);

    if (!rb_profile_reselect(&selected, config, index)) {
        visibility->error_lba = config->error_lba;
        return RB_PROFILE_TEST_SELECTION;
    }
    rb_prepare_profile_test(&prepared, visibility, config, state, *index, rb_disk_read, (void *)0,
        rb_boot.reachable_sectors_low, rb_boot.reachable_sectors_high, admin_lba);

    if (prepared.status == RB_PROFILE_TEST_OK) { rb_handoff(&prepared); }
    return prepared.status;
}
