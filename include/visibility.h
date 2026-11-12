#ifndef RB_VISIBILITY_H
#define RB_VISIBILITY_H

#include "state.h"

enum {
    RB_VISIBILITY_MATCH, RB_VISIBILITY_CHANGE,
    RB_VISIBILITY_PROOF, RB_VISIBILITY_ADMIN
};

typedef struct {
    rb_state_proof proof;
    rb_u32 error_lba;
    rb_u16 status, current_visible, current_active;
    rb_u16 wanted_visible, wanted_active, changed;
    rb_u8 before[512], after[512];
} rb_visibility_result;

/* Read-only preview, never OS-start or write authorization. Only the exact
 * MBR read used by the successful state check may supply the before image.
 * Failed previews expose no MBR images or masks; proof diagnostics remain. */
void rb_visibility_check(rb_visibility_result *result, const rb_config_result *config,
                         const rb_state_result *state, rb_u16 index,
                         rb_sector_reader read, void *opaque,
                         rb_u32 low, rb_u32 high, rb_u32 admin_lba);
rb_u16 __cdecl rb_visibility_selftest(void);

#endif
