#include "backup_links.h"

rb_u16 rb_backup_unlinked_profile(const rb_config *config, const rb_install_state *state)
{
    const rb_profile *profile;
    const rb_installation *installation;
    rb_u16 i, j, found;
    for (i = 0; i < config->count; ++i) {
        profile = &config->entries[i];
        if (!profile->install_low && !profile->install_high) { continue; }
        found = 0;
        for (j = 0; j < state->count; ++j) {
            installation = &state->entries[j];
            if (profile->install_low == installation->install_low && profile->install_high == installation->install_high
                    && profile->slot == installation->slot && profile->type == installation->type
                    && profile->kind == installation->kind && profile->start == installation->start
                    && profile->sectors == installation->sectors
                    && (!profile->approved || installation->phase == RB_INSTALL_READY)) { found = 1; }
        }
        if (!found) { return i; }
    }
    return RB_CONFIG_NONE;
}
