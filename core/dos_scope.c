/* Physical slots eligible for the prepared DOS profile switch. */
#include "dos_scope.h"

static rb_u16 slots_for(const rb_config_result *config, rb_u16 allow_fat32)
{
    rb_u16 i, slots = 0;
    if (config->status || config->copies[0] || config->copies[1]
            || !config->config.count || config->config.count > RB_DOS_PROFILES) { return 0; }
    for (i = 0; i < config->config.count; ++i) {
        const rb_profile *p = &config->config.entries[i];
        /* The parser has already bound the one-bit mask to this physical slot. */
        if (p->kind != 1 || (p->type != 0x06 && !(allow_fat32 && p->type == 0x0B))
                || p->installed != 2 || !p->approved
                || (slots & p->visible_mask)) { return 0; }
        slots |= p->visible_mask;
    }
    return slots;
}

rb_u16 rb_config_dos_slots(const rb_config_result *config)
{
    return slots_for(config, config->config.count > 1);
}

rb_u16 rb_dos_recovery_slots(const rb_config_result *config, const rb_install_state *state)
{
    rb_u16 i;
    for (i = 0; i < state->count; ++i) {
        rb_u16 phase = state->entries[i].phase;
        if (phase != RB_INSTALL_READY && phase != RB_INSTALL_PLANNED) { return 0; }
    }
    /* The external sequence-2 recovery also supports a single enrolled FAT32 primary. */
    return slots_for(config, 1);
}

rb_u16 rb_dos_view_slot(const rb_u8 *mbr, rb_u16 slots)
{
    rb_u16 i, active = 4;
    for (i = 0; i < 4; ++i) {
        const rb_u8 *entry = mbr + 446 + 16 * i;
        rb_u16 type = entry[4];
        if (slots & (1U << i)) {
            if (type == 0x06 || type == 0x0B) {
                if (active != 4 || entry[0] != 0x80) { return 4; }
                active = i;
            } else if ((type != 0x16 && type != 0x1B) || entry[0]) { return 4; }
        } else if (entry[0] || (type && type != 0x05 && type != 0x0F && !(type & 0x10))) {
            return 4;
        }
    }
    return active;
}
