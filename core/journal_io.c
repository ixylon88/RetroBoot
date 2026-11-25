#include "journal_io.h"
#include "admin_audit.h"
#include "state.h"
#ifdef RB_PREPARED_DOS
#include "dos_records.h"
#include "fingerprint.h"
#include "stage2.h"
#endif

static struct {
    rb_admin_audit audit;
    rb_u8 records[2][RB_JOURNAL_BYTES], mbr[512], sector[512];
    rb_config_result config;
    rb_state_result state;
    rb_journal_context context;
    rb_sector_reader read;
    void *opaque;
#ifdef RB_PREPARED_DOS
    rb_dos_record_pair *pair;
    rb_handoff_buffer *trial;
#endif
} work;

static void clear(void *p, rb_u16 n)
{
    rb_u8 *bytes = (rb_u8 *)p;
    while (n) { bytes[--n] = 0; }
}
static rb_u16 same(const rb_u8 *a, const rb_u8 *b, rb_u16 n)
{
    while (n) { --n; if (a[n] != b[n]) { return 0; } } return 1;
}
static rb_u16 __cdecl capture(rb_u32 lba, rb_u8 *sector, void *opaque)
{
    rb_u16 i, code;
    (void)opaque;
    code = work.read(lba, sector, work.opaque);
#ifdef RB_PREPARED_DOS
    if (!code && work.pair) { rb_fingerprint_sector(work.pair->allocation, lba, sector); }
#endif
    if (!code && !lba) { for (i = 0; i < 512; ++i) { work.mbr[i] = sector[i]; } }
    return code;
}
#ifdef RB_PREPARED_DOS
static void capture_pair(rb_u16 file, rb_u16 source)
{
    rb_u16 i, j;
    work.pair->source = source;
    for (i = 0; i < 2; ++i) {
        work.pair->lba[i] = work.audit.files[file + i].first_lba;
        for (j = 0; j < 512; ++j) { work.pair->copies[i][j] = work.records[i][j]; }
    }
}
#endif
static void fail(rb_journal_diagnosis *r, rb_u16 status, rb_u16 detail, rb_u32 lba)
{
    clear(r, sizeof(*r));
    r->status = status; r->detail = detail; r->error_lba = lba;
    r->journal.status = RB_JOURNAL_UNAVAILABLE; r->journal.source = RB_JOURNAL_NONE;
    r->journal.copies[0] = r->journal.copies[1] = RB_JOURNAL_MISSING;
}

static void load(rb_journal_diagnosis *r, rb_u32 low, rb_u32 high,
                  rb_u32 disk_id, rb_u32 admin_lba, rb_u16 mode, rb_u16 heads, rb_u16 spt)
{
    const rb_partition *admin = (const rb_partition *)0;
    rb_u16 i, copy, mask = 0;
    rb_u32 lba;
    fail(r, RB_JLOAD_OK, 0, 0);
    if (rb_audit_admin(&work.audit, capture, (void *)0, low, high, disk_id, admin_lba)) {
        fail(r, RB_JLOAD_ALLOCATION, work.audit.status, work.audit.error_lba); return;
    }
    work.context.scan = &work.audit.scan;
    for (i = 4; i < work.audit.scan.count; ++i) {
        if (work.audit.scan.entries[i].start == admin_lba) {
            admin = &work.audit.scan.entries[i]; work.context.admin_index = i;
        }
    }
    if (!admin) { fail(r, RB_JLOAD_IDENTITY, 0, admin_lba); return; }
    for (i = 0; i < 4; ++i) {
        lba = work.audit.files[i + 2].first_lba;
        if (work.read(lba, work.records[i % 2], work.opaque)) { fail(r, RB_JLOAD_IO, i + 3, lba); return; }
        if (i == 1) {
            rb_config_select(&work.config, work.records[0], work.records[1], 3, &work.audit.scan, admin);
            if (work.config.status || work.config.copies[0] || work.config.copies[1]) {
                fail(r, RB_JLOAD_CONFIG, work.config.status ? work.config.status
                    : work.config.copies[0] ? work.config.copies[0] : work.config.copies[1],
                    work.config.status == RB_CONFIG_CONFLICT ? 0 : work.audit.files[work.config.copies[0] ? 2 : 3].first_lba); return;
            }
            if (work.config.config.version != 2 || work.records[0][8] != 2 || work.records[1][8] != 2
                    || !same(work.records[0] + 48, work.records[1] + 48, 16)) {
                fail(r, RB_JLOAD_IDENTITY, 1, 0); return;
            }
#ifdef RB_PREPARED_DOS
            if (work.trial) {
                if (!rb_dos_config_pair_valid(work.records[0], work.records[1], work.config.source)) {
                    fail(r, RB_JLOAD_CONFIG, RB_CONFIG_CONFLICT, lba); return;
                }
                for (copy = 0; copy < 2; ++copy) {
                    rb_fingerprint_sector(work.pair->allocation, work.audit.files[2 + copy].first_lba, work.records[copy]);
                }
            } else if (work.pair) { capture_pair(2, work.config.source); }
#endif
            for (copy = 0; copy < 16; ++copy) { work.context.media_id[copy] = work.config.config.media_id[copy]; }
        } else if (i == 3) {
            rb_state_select(&work.state, work.records[0], work.records[1], 3, &work.audit.scan, admin);
            if (work.state.status || work.state.copies[0] || work.state.copies[1]) {
                fail(r, RB_JLOAD_STATE, work.state.status ? work.state.status
                    : work.state.copies[0] ? work.state.copies[0] : work.state.copies[1],
                    work.state.status == RB_CONFIG_CONFLICT ? 0 : work.audit.files[work.state.copies[0] ? 4 : 5].first_lba); return;
            }
#ifdef RB_PREPARED_DOS
            if (work.trial) { capture_pair(4, work.state.source); }
            else if (work.pair) {
                if (!same(work.records[0], work.records[1], 512)) { fail(r, RB_JLOAD_STATE, 0, lba); return; }
                rb_fingerprint_sector(work.pair->allocation, lba, work.records[1]);
            }
#endif
            if (!same(work.context.media_id, work.records[0] + 48, 16)
                    || !same(work.context.media_id, work.records[1] + 48, 16)) {
                fail(r, RB_JLOAD_IDENTITY, 2, 0); return;
            }
        }
    }
    work.context.capacity_low = low; work.context.capacity_high = high;
    work.context.io_mode = mode; work.context.heads = heads; work.context.sectors_per_track = spt;
    clear(work.records, sizeof(work.records));
    for (copy = 0; copy < 2; ++copy) {
        for (i = 0; i < 3; ++i) {
            lba = work.audit.journal_lba[copy][i];
            if (work.read(lba, work.records[copy] + i * 512, work.opaque)) {
                r->status = RB_JLOAD_IO; r->detail = copy + 7; r->error_lba = lba; break;
            }
        }
        if (i == 3) { mask |= 1U << copy; }
    }
    if (work.read(0, work.sector, work.opaque)) { fail(r, RB_JLOAD_IO, 0, 0); return; }
    if (!same(work.mbr, work.sector, 512)) { fail(r, RB_JLOAD_CHANGED, 0, 0); return; }
    rb_journal_inspect(&r->journal, work.records[0], work.records[1], mask, &work.context, work.mbr);
}

void rb_journal_load(rb_journal_diagnosis *r, rb_sector_reader read, void *opaque,
                     rb_u32 low, rb_u32 high, rb_u32 disk_id, rb_u32 admin_lba,
                     rb_u16 mode, rb_u16 heads, rb_u16 spt)
{
    clear(&work, sizeof(work)); work.read = read; work.opaque = opaque;
    load(r, low, high, disk_id, admin_lba, mode, heads, spt);
    clear(&work, sizeof(work));
}

#ifdef RB_PREPARED_DOS
static rb_u32 dword(const rb_u8 *p)
{
    return (rb_u32)p[0] | ((rb_u32)p[1] << 8) | ((rb_u32)p[2] << 16) | ((rb_u32)p[3] << 24);
}

static rb_u16 prepared_layout(const rb_profile *entry)
{
    const rb_partition *p = work.audit.scan.entries;
    rb_u16 i, dos = entry->slot - 1, ext = dos == 3 ? 2 : 3;
    if (work.audit.scan.count != 5 || work.audit.scan.ebr_count != 1 || dos >= 4
            || p[dos].type != 6 || p[dos].flag != 0x80 || p[ext].type != 5 || p[ext].flag
            || p[ext].start <= p[dos].start + (p[dos].sectors - 1) || p[4].type != 0x16 || p[4].flag
            || p[4].start + (p[4].sectors - 1) != p[ext].start + (p[ext].sectors - 1)) { return 0; }
    for (i = 0; i < 4; ++i) {
        if (i != dos && i != ext && p[i].type) { return 0; }
    }
    return 1;
}

static rb_u16 __cdecl trial_vbr(rb_u32 lba, rb_u8 *sector, void *opaque)
{
    rb_u16 i, result = capture(lba, sector, opaque);
    if (!result) { for (i = 0; i < 512; ++i) { work.trial->sector[i] = sector[i]; } }
    return result;
}

static rb_u16 stage_trial(const rb_profile *p, rb_u32 low, rb_u32 high)
{
    const rb_installation *entry = &work.state.state.entries[0];
    rb_volume_probe volume;
    rb_u16 i, offset = 446 + (p->slot - 1) * 16;
    /* The caller checked the complete single-DOS layout and both record
       families. All non-READY phases retain a zero VBR claim on disk. */
    if (entry->install_low != p->install_low || entry->install_high != p->install_high
            || entry->slot != p->slot || entry->type != p->type || entry->kind != p->kind
            || entry->start != p->start || entry->sectors != p->sectors) { return RB_TRIAL_HISTORY; }
    if (rb_probe_volume(&volume, &work.audit.scan.entries[p->slot - 1], trial_vbr, 0, low, high)) {
        return RB_TRIAL_VBR;
    }
    if (!rb_dos_geometry_matches(p, work.trial->sector)) { return RB_TRIAL_GEOMETRY; }
    for (i = 0; i < 16; ++i) { work.trial->entry[i] = work.mbr[offset + i]; }
    work.trial->status = work.trial->detail = 0;
    return RB_TIMER_OK;
}

rb_u16 rb_dos_observe(rb_dos_record_pair *pair, const rb_profile_selection *selection,
                      const rb_loader_snapshot *snapshot, rb_handoff_buffer *trial)
{
    rb_journal_diagnosis journal;
    rb_state_proof proof;
    rb_u16 index, status = RB_TIMER_DISK;
    rb_u32 low = rb_boot.reachable_sectors_low, high = rb_boot.reachable_sectors_high;
    clear(pair, sizeof(*pair));
    if (rb_boot.drive != 0x80 || rb_boot.io_mode != 1) { return status; }
    clear(&work, sizeof(work));
    work.read = rb_disk_read; work.pair = pair; work.trial = trial;
    load(&journal, low, high, dword(snapshot->mbr + 440), dword(snapshot->mbr + 436), 1, 0, 0);
    if (!journal.status && !journal.journal.status && journal.journal.observation == RB_TX_BASELINE
            && same(snapshot->mbr, work.mbr, 512) && work.config.config.count == 1
            && work.state.state.count == 1 && rb_profile_reselect(selection, &work.config, &index)
            && work.config.config.default_id == selection->entry.id && selection->entry.kind == 1
            && prepared_layout(&selection->entry)) {
        if (trial) { status = stage_trial(&selection->entry, low, high); }
        else {
            rb_state_check(&proof, &work.config, &work.state, index, capture, (void *)0, low, high);
            if (!proof.status && same(snapshot->mbr, work.mbr, 512)) { status = RB_TIMER_OK; }
        }
    }
    clear(&work, sizeof(work));
    if (status) { clear(pair, sizeof(*pair)); }
    return status;
}
#endif
