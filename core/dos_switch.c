#include "dos_switch.h"
#include "dos_records.h"
#include "stage2.h"

typedef struct {
    rb_switch_disk disk;
    const rb_switch_review *review;
    const rb_loader_snapshot *snapshot;
    const rb_visibility_result *plan;
    const rb_u8 *expected[2][3], *live;
} transaction;

static rb_u16 same(const void *left, const void *right, rb_u16 n)
{
    const rb_u8 *a = left, *b = right;
    while (n) { --n; if (a[n] != b[n]) { return 0; } }
    return 1;
}

static void copy(void *dest, const void *source, rb_u16 n)
{
    rb_u8 *d = dest;
    const rb_u8 *s = source;
    while (n) { --n; d[n] = s[n]; }
}

static void put32(rb_u8 *p, rb_u32 value)
{
    rb_u16 i;
    for (i = 0; i < 4; ++i) { p[i] = (rb_u8)value; value >>= 8; }
}

static rb_u16 target_index(const rb_switch_disk *disk, const rb_dos_choice *choice,
                           rb_u16 selected, rb_u16 *target)
{
    rb_state_proof proof;
    rb_u16 i, index;
    if (choice->count < 2 || choice->count > RB_DOS_PROFILES || selected >= choice->count
            || disk->config->config.count != choice->count) { return 0; }
    for (i = 0; i < choice->count; ++i) {
        if (!rb_profile_reselect(&choice->profiles[i], disk->config, &index)) { return 0; }
        rb_state_check_records(&proof, disk->config, disk->state, index);
        if (proof.status) { return 0; }
        if (i == selected) { *target = index; }
    }
    return 1;
}

static rb_u16 prove_plan(const rb_switch_disk *disk, const rb_dos_choice *choice,
                         rb_u16 selected, const rb_visibility_result *shown, rb_handoff_buffer *handoff)
{
    rb_visibility_result fresh;
    rb_u8 *sector = handoff ? handoff->sector : rb_dos_buffers.transaction.sector;
    rb_u32 low = rb_boot.reachable_sectors_low, high = rb_boot.reachable_sectors_high;
    rb_u16 index;
    if (!target_index(disk, choice, selected, &index)) { return 0; }
    if (handoff) {
        if (rb_stage_profile(handoff, &fresh, disk->config, disk->state, index, rb_disk_read, 0,
                low, high, disk->admin_lba)
                || !same(fresh.before, shown->after, 512)) { return 0; }
    } else {
        rb_visibility_check(&fresh, disk->config, disk->state, index, rb_disk_read, 0,
                            low, high, disk->admin_lba);
        if (fresh.status != RB_VISIBILITY_CHANGE || !same(fresh.before, shown->before, 512)
                || !same(fresh.after, shown->after, 512)
                || rb_disk_read(choice->profiles[selected].entry.start, sector, 0)) { return 0; }
    }
    if (fresh.proof.observed_crc != shown->proof.observed_crc
            || rb_crc32(sector, 512) != fresh.proof.observed_crc
            || !rb_dos_geometry_matches(&choice->profiles[selected].entry, sector)) { return 0; }
    return 1;
}

rb_u16 rb_switch_open(rb_switch_review *review, const rb_dos_choice *choice, rb_u16 selected,
                      const rb_loader_snapshot *snapshot, const rb_visibility_result *shown)
{
    rb_switch_disk disk;
    const rb_journal_result *j = &disk.diagnosis.journal;
    rb_u16 i;
    review->armed = 0;
    if (shown->status != RB_VISIBILITY_CHANGE || !rb_switch_read(&disk, snapshot) || j->status
            || (j->observation != RB_TX_BASELINE && j->observation != RB_TX_COMMITTED_NEW)
            || !same(disk.mbr, snapshot->mbr, 512) || !same(disk.mbr, shown->before, 512)
            || !same(disk.slots[0] + 512, disk.slots[1] + 512, 1024)
            || !same(disk.slots[0] + 1024, disk.mbr, 512)
            || !prove_plan(&disk, choice, selected, shown, 0)) { return RB_SWITCH_CHANGED; }
    if (j->record.sequence == 0xFFFFFFFFUL) { return RB_SWITCH_FULL; }
    review->sequence = j->record.sequence + 1;
    review->prepare = 1 - j->source;
    copy(review->lba, disk.lba, sizeof(review->lba));
    copy(review->ownership, disk.ownership, sizeof(review->ownership));
    for (i = 0; i < 2; ++i) { copy(rb_dos_buffers.transaction.headers[i], disk.slots[i], 512); }
    copy(rb_dos_buffers.transaction.previous, disk.slots[0] + 512, 512);
    review->armed = 1;
    return RB_SWITCH_OK;
}

/* During publication a partially replaced slot may intentionally be undecodable.
 * Compare all six complete sectors to the exact current step, including the
 * peer. A usable journal is separately required before sector zero and boot. */
static rb_u16 reload(transaction *t)
{
    rb_u16 i, s;
    if (!rb_switch_read(&t->disk, t->snapshot)
            || !same(t->disk.ownership, t->review->ownership, sizeof(t->review->ownership))
            || !same(t->disk.lba, t->review->lba, sizeof(t->review->lba))
            || !same(t->disk.mbr, t->live, 512)) { return RB_SWITCH_CHANGED; }
    for (s = 0; s < 2; ++s) {
        for (i = 0; i < 3; ++i) {
            if (!same(t->disk.slots[s] + i * 512, t->expected[s][i], 512)) { return RB_SWITCH_CHANGED; }
        }
    }
    return RB_SWITCH_OK;
}

static rb_u16 write_checked(rb_u32 lba, const rb_u8 *old, const rb_u8 *next)
{
    rb_u8 *actual = rb_dos_buffers.transaction.sector;
    if (rb_disk_read(lba, actual, 0) || !same(actual, old, 512)) { return RB_SWITCH_CHANGED; }
    if (lba ? rb_dos_write_record(lba, next) : rb_dos_write_mbr(next)) { return RB_SWITCH_IO; }
    if (rb_disk_read(lba, actual, 0) || !same(actual, next, 512)) { return RB_SWITCH_IO; }
    return RB_SWITCH_OK;
}

static rb_u16 publish(transaction *t, rb_u16 slot, rb_u16 phase)
{
    rb_u8 *header = rb_dos_buffers.transaction.headers[slot];
    const rb_u8 *old, *next;
    rb_u16 i, index, code;
    /* Publish both complete snapshots before their header. Skip an already
       identical sector only after the exact physical preimage was checked. */
    for (i = 0; i < 3; ++i) {
        index = (i + 1) % 3;
        if (index == 1) { next = t->plan->before; }
        else if (index == 2) { next = t->plan->after; }
        else {
            put32(header + 16, t->review->sequence);
            header[36] = (rb_u8)phase;
            put32(header + 64, rb_crc32(t->plan->before, 512));
            put32(header + 68, rb_crc32(t->plan->after, 512));
            put32(header + 508, rb_crc32(header, 508));
            next = header;
        }
        old = t->disk.slots[slot] + index * 512;
        t->expected[slot][index] = next;
        if (same(old, next, 512)) { continue; }
        code = write_checked(t->review->lba[slot][index], old, next);
        if (!code) { code = reload(t); }
        if (code) { return code; }
    }
    return RB_SWITCH_OK;
}

static rb_u16 observed(const transaction *t, rb_u16 state, rb_u16 slot)
{
    const rb_journal_result *j = &t->disk.diagnosis.journal;
    return !j->status && j->observation == state && j->source == slot
        && j->record.sequence == t->review->sequence && j->record.changed == t->plan->changed;
}

static rb_u16 start_committed(const transaction *t, const rb_dos_choice *choice, rb_u16 selected)
{
    rb_handoff_buffer boot;
    if (!observed(t, RB_TX_COMMITTED_NEW, 1 - t->review->prepare)
            || !prove_plan(&t->disk, choice, selected, t->plan, &boot)) { return RB_SWITCH_CHANGED; }
    rb_video_console();
    rb_handoff(&boot);
    return RB_SWITCH_OK;
}

rb_u16 rb_switch_apply(rb_switch_review *review, const rb_dos_choice *choice, rb_u16 selected,
                       const rb_loader_snapshot *snapshot, const rb_visibility_result *shown)
{
    transaction t;
    rb_u16 s, code, prepare = review->prepare;
    if (!review->armed) { return RB_SWITCH_CHANGED; }
    review->armed = 0;
    t.review = review; t.snapshot = snapshot; t.plan = shown; t.live = shown->before;
    for (s = 0; s < 2; ++s) {
        t.expected[s][0] = rb_dos_buffers.transaction.headers[s];
        t.expected[s][1] = rb_dos_buffers.transaction.previous;
        t.expected[s][2] = shown->before;
    }
    if (reload(&t) || !prove_plan(&t.disk, choice, selected, shown, 0)) { return RB_SWITCH_CHANGED; }
    code = publish(&t, prepare, RB_TX_PREPARED);
    if (code) { return code; }
    if (!observed(&t, RB_TX_PREPARED_OLD, prepare)
            || !prove_plan(&t.disk, choice, selected, shown, 0)) { return RB_SWITCH_CHANGED; }
    code = write_checked(0, shown->before, shown->after);
    if (code) { return code; }
    t.live = shown->after;
    if (reload(&t) || !observed(&t, RB_TX_PREPARED_NEW, prepare)) { return RB_SWITCH_CHANGED; }
    code = publish(&t, 1 - prepare, RB_TX_COMMITTED);
    if (code) { return code; }
    return start_committed(&t, choice, selected);
}
