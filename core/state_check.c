#include "state.h"

typedef struct { rb_sector_reader read; void *opaque; rb_u32 crc; } captured_crc;

static rb_u16 __cdecl capture(rb_u32 lba, rb_u8 *sector, void *opaque)
{
    captured_crc *c = (captured_crc *)opaque;
    rb_u16 status = c->read(lba, sector, c->opaque);
    if (!status) { c->crc = rb_crc32(sector, 512); }
    return status;
}

static void failed(rb_state_proof *r, rb_u16 status, rb_u16 detail, rb_u32 lba)
{
    r->status = status; r->detail = detail; r->error_lba = lba;
    r->observed_crc = 0; r->matched_index = RB_CONFIG_NONE;
}

void rb_state_check(rb_state_proof *r, const rb_config_result *config,
                    const rb_state_result *state, rb_u16 index, rb_sector_reader read,
                    void *opaque, rb_u32 low, rb_u32 high)
{
    rb_partition_scan scan;
    rb_volume_probe volume;
    captured_crc c;
    const rb_profile *profile;
    const rb_partition *target;
    const rb_installation *entry = (const rb_installation *)0;
    rb_u16 i, found = RB_CONFIG_NONE;
    failed(r, RB_PROOF_MATCH, 0, 0);
    if (config->status || config->config.count > 8) { failed(r, RB_PROOF_CONFIG, config->status, config->error_lba); return; }
    if (state->status || state->state.count > 4) { failed(r, RB_PROOF_STATE, state->status, state->error_lba); return; }
    if (config->copies[0] || config->copies[1] || state->copies[0] || state->copies[1]) {
        failed(r, RB_PROOF_DEGRADED, 0, state->error_lba ? state->error_lba : config->error_lba); return;
    }
    if (config->config.version != 2) { failed(r, RB_PROOF_LEGACY, 0, 0); return; }
    if (config->config.disk_id != state->state.disk_id || config->config.layout_crc != state->state.layout_crc) {
        failed(r, RB_PROOF_IDENTITY, 0, 0); return;
    }
    for (i = 0; i < 16; ++i) {
        if (config->config.media_id[i] != state->state.media_id[i]) { failed(r, RB_PROOF_IDENTITY, 0, 0); return; }
    }
    if (index >= config->config.count) { failed(r, RB_PROOF_EMPTY, 0, 0); return; }
    profile = &config->config.entries[index];
    for (i = 0; i < state->state.count; ++i) {
        if (state->state.entries[i].phase != RB_INSTALL_PLANNED && state->state.entries[i].phase != RB_INSTALL_READY) {
            failed(r, RB_PROOF_PENDING, state->state.entries[i].phase, 0); return;
        }
        if ((profile->install_low || profile->install_high)
                && state->state.entries[i].install_low == profile->install_low
                && state->state.entries[i].install_high == profile->install_high) {
            entry = &state->state.entries[i]; found = i;
        }
    }
    if (!entry) { failed(r, RB_PROOF_INSTALLATION, 0, 0); return; }
    if (entry->slot != profile->slot || entry->start != profile->start || entry->sectors != profile->sectors
            || entry->type != profile->type || entry->kind != profile->kind) { failed(r, RB_PROOF_TARGET, 0, 0); return; }
    if (entry->phase != RB_INSTALL_READY) { failed(r, RB_PROOF_NOT_READY, entry->phase, 0); return; }
    if (profile->installed != 2 || !profile->approved) { failed(r, RB_PROOF_APPROVAL, 0, 0); return; }
    rb_scan_partitions(&scan, read, opaque, low, high, state->state.disk_id);
    if (scan.status) { failed(r, RB_PROOF_SCAN, scan.status, scan.error_lba); return; }
    if (rb_layout_crc(&scan) != state->state.layout_crc || profile->slot < 1 || profile->slot > 4) {
        failed(r, RB_PROOF_LAYOUT, 0, 0); return;
    }
    target = &scan.entries[profile->slot - 1];
    if (target->start != profile->start || target->sectors != profile->sectors
            || (target->type != profile->type && target->type != profile->type + 0x10)) {
        failed(r, RB_PROOF_LAYOUT, 0, 0); return;
    }
    c.read = read; c.opaque = opaque; c.crc = 0;
    rb_probe_volume(&volume, target, capture, &c, low, high);
    if (volume.status) { failed(r, RB_PROOF_VOLUME, volume.status, profile->start); return; }
    if (c.crc != entry->vbr_crc) { failed(r, RB_PROOF_VBR, 0, profile->start); return; }
    r->observed_crc = c.crc; r->matched_index = found;
}
