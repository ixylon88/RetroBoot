#include "dos_boot.h"
#include "stage2.h"

static rb_u16 word(const rb_u8 *p)
{
    return (rb_u16)p[0] | ((rb_u16)p[1] << 8);
}

static rb_u32 dword(const rb_u8 *p)
{
    return (rb_u32)word(p) | ((rb_u32)word(p + 2) << 16);
}

static void load_config(rb_config_result *config, const rb_loader_snapshot *snapshot)
{
    rb_config_load(config, rb_disk_read, (void *)0, rb_boot.reachable_sectors_low,
        rb_boot.reachable_sectors_high, dword(snapshot->mbr + 440), dword(snapshot->mbr + 436));
}

static rb_u16 supported(const rb_config_result *config)
{
    rb_u16 i, slots = 0;
    if (config->status || config->copies[0] || config->copies[1]
            || !config->config.count || config->config.count > RB_DOS_PROFILES) { return 0; }
    for (i = 0; i < config->config.count; ++i) {
        const rb_profile *p = &config->config.entries[i];
        /* The parser has already bound the one-bit mask to this physical slot. */
        if (p->kind != 1 || p->type != 6 || p->installed != 2 || !p->approved
                || (slots & p->visible_mask)) { return 0; }
        slots |= p->visible_mask;
    }
    return 1;
}

void rb_dos_open(rb_dos_choice *choice, rb_config_result *config,
                 rb_state_result *state, const rb_loader_snapshot *snapshot)
{
    rb_u16 i;
    load_config(config, snapshot);
    choice->count = choice->default_index = choice->countdown = choice->trial = 0;
    choice->records.status = RB_PROOF_MATCH;
    if (!supported(config)) { return; }
    rb_state_load(state, rb_disk_read, (void *)0, rb_boot.reachable_sectors_low,
                  rb_boot.reachable_sectors_high, dword(snapshot->mbr + 440), dword(snapshot->mbr + 436));
    for (i = 0; i < config->config.count; ++i) {
        const rb_profile *p = &config->config.entries[i];
        rb_state_check_records(&choice->records, config, state, i);
        if (choice->records.status) {
            if (config->config.count == 1 && choice->records.status == RB_PROOF_PENDING
                    && choice->records.detail == RB_INSTALL_RECOVERY && state->state.count == 1
                    && config->config.default_id == p->id) {
                rb_profile_remember(&choice->profiles[0], config, 0);
                choice->trial = choice->profiles[0].valid;
            }
            return;
        }
        rb_profile_remember(&choice->profiles[i], config, i);
        if (config->config.default_id == p->id) {
            choice->default_index = i;
            if (config->config.count == 1) { choice->countdown = config->config.countdown; }
        }
    }
    choice->count = config->config.count;
}

rb_u16 rb_dos_geometry_matches(const rb_profile *entry, const rb_u8 *sector)
{
    rb_u16 geometry[3];
    rb_u32 reach;
    rb_dos_geometry(geometry);
    reach = (rb_u32)geometry[0] * geometry[1] * geometry[2];
    return geometry[1] == word(sector + 26) && geometry[2] == word(sector + 24)
        && entry->start < reach && entry->sectors <= reach - entry->start;
}

rb_u16 rb_dos_start(const rb_dos_choice *choice, rb_u16 selection, rb_u16 automatic, rb_u16 *index,
                    rb_config_result *config, rb_state_result *state, rb_visibility_result *visibility,
                    rb_journal_diagnosis *journal, const rb_loader_snapshot *snapshot)
{
    rb_handoff_buffer prepared;
    const rb_profile_selection *target;
    rb_u16 status, i;
    rb_u32 mbr_crc;
    rb_u32 disk_id = dword(snapshot->mbr + 440), admin = dword(snapshot->mbr + 436);
    rb_u32 low = rb_boot.reachable_sectors_low, high = rb_boot.reachable_sectors_high;

    load_config(config, snapshot);
    if (selection >= choice->count || !supported(config) || config->config.count != choice->count) {
        return RB_PROFILE_SELECTION;
    }
    target = &choice->profiles[selection];
    if (!rb_profile_reselect(target, config, index)
            || (automatic && (choice->count != 1 || config->config.default_id != target->entry.id
                              || config->config.countdown != choice->countdown))) {
        return RB_PROFILE_SELECTION;
    }
    rb_state_load(state, rb_disk_read, (void *)0, low, high, disk_id, admin);
    rb_journal_load(journal, rb_disk_read, (void *)0, low, high, disk_id, admin,
        rb_boot.io_mode ? 1 : 2, rb_boot.io_mode ? 0 : (rb_u16)snapshot->heads,
        rb_boot.io_mode ? 0 : (rb_u16)snapshot->sectors_per_track);
    if (journal->status || journal->journal.status) { return RB_DOS_JOURNAL; }
    if (journal->journal.observation == RB_TX_BASELINE) {
        mbr_crc = journal->journal.record.before_crc;
    } else if (choice->count > 1 && journal->journal.observation == RB_TX_COMMITTED_NEW) {
        mbr_crc = journal->journal.record.after_crc;
    } else { return RB_DOS_JOURNAL; }
    status = rb_stage_profile(&prepared, visibility, config, state, *index, rb_disk_read,
                              (void *)0, low, high, admin);
    if (status != RB_PROFILE_OK && status != RB_PROFILE_CHANGE) { return status; }
    if (rb_crc32(visibility->before, 512) != mbr_crc) { return RB_DOS_JOURNAL; }
    for (i = 0; i < 512; ++i) {
        if (visibility->before[i] != snapshot->mbr[i]) { return RB_DOS_JOURNAL; }
    }
    if (status == RB_PROFILE_CHANGE) { return status; }
    /* DOS 6.x continues with CHS even when RetroBoot loaded through EDD. */
    if (!rb_dos_geometry_matches(&target->entry, prepared.sector)) {
        return RB_DOS_GEOMETRY;
    }
    rb_video_console();
    rb_handoff(&prepared);
    return RB_PROFILE_OK;
}
