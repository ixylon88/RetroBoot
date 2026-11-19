#include "profile_test.h"
#include "handoff_fixture.h"

rb_u16 rb_prepare_profile_test(rb_handoff_buffer *r, rb_visibility_result *visibility,
                               const rb_config_result *config, const rb_state_result *state,
                               rb_u16 index, rb_sector_reader read, void *opaque,
                               rb_u32 low, rb_u32 high, rb_u32 admin_lba)
{
    rb_u16 i, status;
    status = rb_stage_profile(r, visibility, config, state, index, read, opaque, low, high, admin_lba);
    if (status) { return status; }

    if (config->config.disk_id != RB_TEST_DISK_ID || config->config.entries[index].slot != 1) {
        status = RB_PROFILE_TARGET;
    }
    for (i = 0; !status && i < 16; ++i) {
        if (r->entry[i] != rb_test_entry[i]) { status = RB_PROFILE_TARGET; }
    }
    for (i = 0; !status && i < 512; ++i) {
        if (r->sector[i] != rb_test_vbr[i]) {
            visibility->error_lba = config->config.entries[index].start;
            status = RB_PROFILE_CODE;
        }
    }
    if (status) {
        rb_u8 *bytes = (rb_u8 *)r;
        for (i = 0; i < sizeof(*r); ++i) { bytes[i] = 0; }
        r->status = status;
    }
    return status;
}
