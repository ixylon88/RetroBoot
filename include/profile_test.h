#ifndef RB_PROFILE_TEST_H
#define RB_PROFILE_TEST_H

#include "profile_boot.h"

enum {
    RB_PROFILE_TEST_OK = RB_PROFILE_OK, RB_PROFILE_TEST_SELECTION = RB_PROFILE_SELECTION,
    RB_PROFILE_TEST_PROOF = RB_PROFILE_PROOF, RB_PROFILE_TEST_CHANGE = RB_PROFILE_CHANGE,
    RB_PROFILE_TEST_TARGET = RB_PROFILE_TARGET, RB_PROFILE_TEST_CODE = RB_PROFILE_CODE
};

/* Test-only staging after freshly loaded records: one current layout/VBR
 * observation, matching visibility and exact compiled T07 bytes. Every failure
 * clears the handoff buffer. This is not an arbitrary OS authorization API. */
rb_u16 rb_prepare_profile_test(rb_handoff_buffer *prepared, rb_visibility_result *visibility,
                               const rb_config_result *config, const rb_state_result *state,
                               rb_u16 index, rb_sector_reader read, void *opaque,
                               rb_u32 low, rb_u32 high, rb_u32 admin_lba);
rb_u16 __cdecl rb_run_profile_test(rb_config_result *config, rb_state_result *state,
                                   rb_visibility_result *visibility, rb_u16 *index,
                                   rb_u32 disk_id, rb_u32 admin_lba);
rb_u16 __cdecl rb_profile_test_selftest(void);

#endif
