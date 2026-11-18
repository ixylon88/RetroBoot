#include "profile_boot.h"

typedef struct {
    rb_sector_reader read;
    void *opaque;
    rb_u32 lba;
    rb_u8 *sector;
} profile_capture;

static rb_u16 same(const rb_u8 *a, const rb_u8 *b, rb_u16 length)
{
    rb_u16 i;
    for (i = 0; i < length; ++i) { if (a[i] != b[i]) { return 0; } }
    return 1;
}

static rb_u16 same_profile(const rb_profile *a, const rb_profile *b)
{
    return a->id == b->id && a->start == b->start && a->sectors == b->sectors
        && a->install_low == b->install_low && a->install_high == b->install_high
        && a->slot == b->slot && a->type == b->type && a->kind == b->kind
        && a->installed == b->installed && a->approved == b->approved
        && a->visible_mask == b->visible_mask
        && same((const rb_u8 *)a->name, (const rb_u8 *)b->name, sizeof(a->name));
}

void rb_profile_remember(rb_profile_selection *s, const rb_config_result *config, rb_u16 index)
{
    rb_u16 i;
    rb_u8 *bytes = (rb_u8 *)s;
    for (i = 0; i < sizeof(*s); ++i) { bytes[i] = 0; }

    if (config->status || config->config.version != 2 || config->config.count > RB_CONFIG_MAX
            || index >= config->config.count || !config->config.entries[index].id) { return; }

    s->disk_id = config->config.disk_id;
    s->layout_crc = config->config.layout_crc;
    for (i = 0; i < 16; ++i) { s->media_id[i] = config->config.media_id[i]; }
    s->entry = config->config.entries[index];
    s->valid = 1;
}

rb_u16 rb_profile_reselect(const rb_profile_selection *s, const rb_config_result *config, rb_u16 *index)
{
    rb_u16 i, found = RB_CONFIG_NONE;
    *index = RB_CONFIG_NONE;

    if (!s->valid || config->status || config->config.version != 2
            || config->config.count > RB_CONFIG_MAX || config->config.disk_id != s->disk_id
            || config->config.layout_crc != s->layout_crc
            || !same(s->media_id, config->config.media_id, 16)) { return 0; }

    for (i = 0; i < config->config.count; ++i) {
        if (config->config.entries[i].id == s->entry.id) {
            if (found != RB_CONFIG_NONE || !same_profile(&s->entry, &config->config.entries[i])) { return 0; }
            found = i;
        }
    }

    if (found == RB_CONFIG_NONE) { return 0; }
    *index = found;
    return 1;
}

static rb_u16 fail(rb_handoff_buffer *r, rb_u16 status)
{
    rb_u16 i;
    rb_u8 *bytes = (rb_u8 *)r;
    for (i = 0; i < sizeof(*r); ++i) { bytes[i] = 0; }
    r->status = status;
    return status;
}

static rb_u16 __cdecl capture_read(rb_u32 lba, rb_u8 *sector, void *opaque)
{
    profile_capture *source = (profile_capture *)opaque;
    rb_u16 i, status = source->read(lba, sector, source->opaque);

    if (!status && lba == source->lba) {
        for (i = 0; i < 512; ++i) { source->sector[i] = sector[i]; }
    }
    return status;
}

rb_u16 rb_stage_profile(rb_handoff_buffer *r, rb_visibility_result *visibility,
                               const rb_config_result *config, const rb_state_result *state,
                               rb_u16 index, rb_sector_reader read, void *opaque,
                               rb_u32 low, rb_u32 high, rb_u32 admin_lba)
{
    profile_capture source;
    rb_u16 i, offset;
    fail(r, RB_PROFILE_OK);
    source.read = read;
    source.opaque = opaque;
    source.sector = r->sector;
    source.lba = index < config->config.count && config->config.count <= RB_CONFIG_MAX
        ? config->config.entries[index].start : 0;

    /* Capture only the VBR read used by this fresh proof. An earlier F7 view
     * never supplies authorization, sector bytes or an entry for the jump. */
    rb_visibility_check(visibility, config, state, index, capture_read, &source, low, high, admin_lba);
    if (visibility->status > RB_VISIBILITY_CHANGE) { return fail(r, RB_PROFILE_PROOF); }
    if (visibility->status != RB_VISIBILITY_MATCH) { return fail(r, RB_PROFILE_CHANGE); }

    offset = 446 + (config->config.entries[index].slot - 1) * 16;
    for (i = 0; i < 16; ++i) { r->entry[i] = visibility->before[offset + i]; }
    return RB_PROFILE_OK;
}
