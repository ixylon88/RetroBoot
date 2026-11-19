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

void rb_dos_open(rb_dos_choice *choice, rb_config_result *config, const rb_loader_snapshot *snapshot)
{
    const rb_profile *p = &config->config.entries[0];
    load_config(config, snapshot);
    choice->selected.valid = 0;
    choice->countdown = 0;
    if (config->status || config->copies[0] || config->copies[1] || config->config.count != 1
            || p->kind != 1 || p->type != 6 || p->installed != 2 || !p->approved) { return; }
    rb_profile_remember(&choice->selected, config, 0);
    if (choice->selected.valid && config->config.default_id == p->id) {
        choice->countdown = config->config.countdown;
    }
}

rb_u16 rb_dos_start(const rb_dos_choice *choice, rb_u16 automatic,
                    rb_config_result *config, rb_state_result *state, rb_visibility_result *visibility,
                    rb_journal_diagnosis *journal, const rb_loader_snapshot *snapshot)
{
    rb_handoff_buffer prepared;
    rb_u16 index, status, geometry[3];
    rb_u32 reach;
    rb_u32 disk_id = dword(snapshot->mbr + 440), admin = dword(snapshot->mbr + 436);
    rb_u32 low = rb_boot.reachable_sectors_low, high = rb_boot.reachable_sectors_high;

    load_config(config, snapshot);
    if (config->config.count != 1 || !rb_profile_reselect(&choice->selected, config, &index)
            || (automatic && (config->config.default_id != choice->selected.entry.id
                              || config->config.countdown != choice->countdown))) {
        return RB_PROFILE_SELECTION;
    }
    rb_state_load(state, rb_disk_read, (void *)0, low, high, disk_id, admin);
    rb_journal_load(journal, rb_disk_read, (void *)0, low, high, disk_id, admin,
        rb_boot.io_mode ? 1 : 2, rb_boot.io_mode ? 0 : (rb_u16)snapshot->heads,
        rb_boot.io_mode ? 0 : (rb_u16)snapshot->sectors_per_track);
    if (journal->status || journal->journal.status || journal->journal.observation != RB_TX_BASELINE) {
        return RB_DOS_JOURNAL;
    }
    status = rb_stage_profile(&prepared, visibility, config, state, index, rb_disk_read,
                              (void *)0, low, high, admin);
    if (status) { return status; }
    if (rb_crc32(visibility->before, 512) != journal->journal.record.before_crc) {
        return RB_DOS_JOURNAL;
    }
    /* DOS 6.x continues with CHS even when RetroBoot loaded through EDD. */
    rb_dos_geometry(geometry);
    reach = (rb_u32)geometry[0] * geometry[1] * geometry[2];
    if (geometry[1] != word(prepared.sector + 26)
            || geometry[2] != word(prepared.sector + 24)
            || choice->selected.entry.start >= reach
            || choice->selected.entry.sectors > reach - choice->selected.entry.start) {
        return RB_DOS_GEOMETRY;
    }
    rb_video_console();
    rb_handoff(&prepared);
    return RB_PROFILE_OK;
}
