/* Independently booted repair of a later HDD profile transaction. */
#include "restore_target.h"
#include "restore_stage1.h"
#include "backup_target.h"
#include "fingerprint.h"
#include "journal.h"

rb_u16 __cdecl rb_ata_write_journal_sector(rb_u32 lba, const rb_u8 *sector);
rb_u16 __cdecl rb_ata_restore_mbr(const rb_u8 *sector);

enum { BAD_BACKUP, BAD_TARGET, BAD_JOURNAL, SETTLED, UNDO, FINISH };
enum { PRE_OLD, PRE_NEW, PRE_HEADER, MBR, END_OLD, END_NEW, END_HEADER, ROWS };

typedef struct {
    rb_u32 sequence;
    rb_u16 prepare, previous, old, target;
} transition;

typedef struct {
    transition tx;
    rb_u16 row, mode;
    rb_u8 before[512], after[512];
} action;

static struct {
    rb_u8 slot[2][RB_JOURNAL_BYTES], live[512];
    rb_u32 map[2][3], digest[2];
    rb_u16 mask, target;
} disk;

static struct {
    rb_ata_enrollment profile;
    rb_u8 publication[STORE_COMMIT_FIELDS];
    rb_u8 *approved;
    rb_u32 map[2][3], digest[2];
} shown;

static int pin(void *field, const void *value, rb_u16 bytes, int first)
{
    if (first) { rb_store_copy(field, value, bytes); return 1; }
    return equal(field, value, bytes);
}

static void put32(rb_u8 *out, rb_u32 value)
{
    rb_u16 i;
    for (i = 0; i < 4; ++i) { out[i] = (rb_u8)value; value >>= 8; }
}

static void hex(rb_u32 value, rb_u16 digits)
{
    static const char alphabet[] = "0123456789ABCDEF";
    while (digits) { rb_putc(alphabet[(value >> (4 * --digits)) & 15]); }
}

/* A torn return to P1 can briefly set two active flags. The external MBR
   supplies the structural view for allocation only. Every actual LBA 0 read
   must still match the complete physical sector observed at entry. */
static rb_u16 __cdecl audit_read(rb_u32 lba, rb_u8 *out, void *unused)
{
    (void)unused;
    if (!read_live(lba, out)) { return 1; }
    if (!lba) {
        if (!equal(out, disk.live, 512)) { return 1; }
        rb_store_copy(out, rb_store.witness.approved, 512);
    }
    rb_fingerprint_sector(disk.digest, lba, out);
    return 0;
}

static int profile_slots(const rb_backup_sources *sources)
{
    const rb_u8 *mbr = rb_store.witness.approved;
    rb_u16 i, j, n = 0;
    disk.mask = 0; disk.target = 4;
    for (i = 0; i < 4; ++i) {
        const rb_u8 *entry = mbr + 446 + 16 * i;
        rb_u16 base = entry[4] & ~0x10U;
        if (entry[4] == 0 || entry[4] == 5 || entry[4] == 15) { continue; }
        if (base != 0x06 && base != 0x0B) { return 0; }
        for (j = 0; j < sources->ready_count; ++j) {
            if (sources->ready[j].start == sources->scan.entries[i].start) { break; }
        }
        if (j == sources->ready_count) { return 0; }
        if (entry[4] == base) {
            if (entry[0] != 0x80 || disk.target != 4) { return 0; }
            disk.target = i;
        } else if (entry[0]) { return 0; }
        disk.mask |= 1U << i; ++n;
    }
    return n >= 2 && n <= 3 && n == sources->ready_count && disk.target < 4;
}

static int open_disk(rb_u16 drive, int first, rb_journal_context *ctx, rb_backup_sources *sources)
{
    const rb_backup *saved;
    rb_backup_target target;
    rb_u8 data[512], external[512];
    rb_u32 j;
    rb_u16 i, s;
    if (rb_store_open(drive) != RB_STORE_OCCUPIED || !(saved = rb_store_verify())) { return BAD_BACKUP; }
    if (!rb_store_probe_source() || !rb_ata_target_can_flush(&rb_store.profile)
            || !mbr_only(saved, data) || !read_live(0, disk.live)
            || !equal(rb_store.witness.approved, stage1_code, sizeof(stage1_code))) { return BAD_TARGET; }

    disk.digest[0] = disk.digest[1] = 0;
    rb_backup_match_sources(&target, sources, saved, &rb_store.source.device, audit_read, 0);
    if (target.status || !profile_slots(sources)) { return BAD_TARGET; }
    /* Compare the saved EBR(s), VBR(s) and both raw configuration/state
       records. Backup extents are read-only and never select a write address. */
    for (i = 2; i < saved->count; ++i) {
        const rb_backup_extent *e = &saved->entries[i];
        for (j = 0; j < e->sectors; ++j) {
            if (!read_live(e->lba + j, data) || rb_store_file_read(e->file_sector + j, external, 0)
                    || !equal(data, external, 512)) { return BAD_TARGET; }
        }
    }
    rb_store_copy((rb_u8 *)disk.map, (const rb_u8 *)sources->journal_lba, sizeof(disk.map));
    if (!pin(&shown.profile, &rb_store.profile, sizeof(shown.profile), first)
            || !pin(shown.publication, rb_store.metadata, sizeof(shown.publication), first)
            || !pin(shown.approved, rb_store.witness.approved, 512, first)
            || !pin(shown.map, disk.map, sizeof(disk.map), first)
            || !pin(shown.digest, disk.digest, sizeof(disk.digest), first)) { return BAD_TARGET; }
    ctx->scan = &sources->scan;
    for (i = 4; i < sources->scan.count && sources->scan.entries[i].start != target.admin_start; ++i) {}
    ctx->admin_index = i; ctx->io_mode = 1; ctx->heads = ctx->sectors_per_track = 0;
    ctx->capacity_low = saved->capacity_low; ctx->capacity_high = saved->capacity_high;
    rb_store_copy(ctx->media_id, target.media_id, 16);
    for (s = 0; s < 2; ++s) {
        for (i = 0; i < 3; ++i) {
            if (!read_live(disk.map[s][i], disk.slot[s] + 512 * i)) { return BAD_JOURNAL; }
        }
    }
    return same_source() && read_live(0, data) && equal(data, disk.live, 512) ? SETTLED : BAD_TARGET;
}

static void view(rb_u8 *out, rb_u16 selected)
{
    rb_u16 i;
    rb_store_copy(out, shown.approved, 512);
    for (i = 0; i < 4; ++i) {
        if (disk.mask & (1U << i)) {
            rb_u8 *entry = out + 446 + 16 * i;
            entry[0] = i == selected ? 0x80 : 0;
            entry[4] = (entry[4] & ~0x10U) | (i == selected ? 0 : 0x10);
        }
    }
}

static rb_u16 active_slot(const rb_u8 *mbr)
{
    rb_u16 i;
    for (i = 0; i < 4; ++i) {
        if ((disk.mask & (1U << i)) && mbr[446 + 16 * i] == 0x80) { break; }
    }
    return i;
}

static int matches_view(const rb_u8 *mbr, rb_u16 slot)
{
    rb_u8 expected[512];
    if (slot >= 4 || !(disk.mask & (1U << slot))) { return 0; }
    view(expected, slot);
    return equal(expected, mbr, 512);
}

static void header(rb_u8 *out, const rb_u8 *anchor, rb_u32 seq, rb_u16 phase,
                   const rb_u8 *before, const rb_u8 *after)
{
    rb_store_copy(out, anchor, 512);
    put32(out + 16, seq); out[36] = (rb_u8)phase;
    put32(out + 64, rb_crc32(before, 512)); put32(out + 68, rb_crc32(after, 512));
    put32(out + 508, rb_crc32(out, 508));
}

static rb_u16 index_for(rb_u16 row) { return (row % 4 + 1) % 3; }

static rb_u32 address(const transition *tx, rb_u16 row)
{
    return row == MBR ? 0 : disk.map[row < MBR ? tx->prepare : 1 - tx->prepare][index_for(row)];
}

static const rb_u8 *physical(const transition *tx, rb_u16 row)
{
    return row == MBR ? disk.live : disk.slot[row < MBR ? tx->prepare : 1 - tx->prepare] + 512 * index_for(row);
}

/* A forward tear is one new prefix and old suffix. Restoring a partly
   copied snapshot can also leave old bytes at the beginning of that prefix. */
static int partial(const rb_u8 *actual, const rb_u8 *next, const rb_u8 *old, int restoring)
{
    rb_u16 i = 0;
    if (restoring) { while (i < 512 && actual[i] == old[i]) { ++i; } }
    while (i < 512 && actual[i] == next[i]) { ++i; }
    return equal(actual + i, old + i, 512 - i);
}

static void set_action(action *a, rb_u16 row, const rb_u8 *actual, const rb_u8 *next)
{
    a->row = row;
    rb_store_copy(a->before, actual, 512); rb_store_copy(a->after, next, 512);
}

/* The seven rows are physical publication order. All rows after the first
   unfinished one must still equal their exact old sectors. */
static int match(action *a, const rb_u8 *anchor)
{
    const transition *t = &a->tx;
    rb_u8 previous[512], old[512], old_header[512], new_header[512];
    const rb_u8 *from, *to, *actual, *approved = shown.approved;
    rb_u16 row, phase;
    int same_old;
    view(previous, t->previous); view(old, t->old);
    a->row = ROWS; a->mode = FINISH;
    for (row = 0; row < ROWS; ++row) {
        actual = physical(t, row);
        if (row == PRE_HEADER || row == END_HEADER) {
            phase = row == PRE_HEADER ? RB_TX_PREPARED : RB_TX_COMMITTED;
            header(old_header, anchor, t->sequence - 1, phase, previous, old);
            header(new_header, anchor, t->sequence, phase, old, approved);
            from = old_header; to = new_header;
        } else if (row == PRE_OLD || row == END_OLD) {
            from = previous; to = old;
        } else {
            from = old; to = approved;
        }
        same_old = equal(actual, from, 512);
        if (a->row != ROWS) {
            if (!same_old) { return 0; }
        } else if (!equal(actual, to, 512)) {
            if (!same_old && !partial(actual, to, from, 0)
                    && !(row == PRE_OLD && partial(actual, to, from, 1))
                    && !(row == PRE_NEW && rb_journal_unfinished_snapshot(actual, to, from))) { return 0; }
            if (row == PRE_OLD || row == PRE_NEW) {
                if (row == PRE_OLD && same_old) { return 0; } /* No attempted switch. */
                a->mode = UNDO;
                if (row == PRE_NEW && same_old) {
                    set_action(a, PRE_OLD, physical(t, PRE_OLD), previous);
                } else { set_action(a, row, actual, from); }
            } else { set_action(a, row, actual, to); }
        }
    }
    return a->row < ROWS;
}

static int inspect(rb_u16 drive, action *a, const transition *pinned)
{
    rb_backup_sources sources;
    rb_journal_context ctx;
    rb_journal_result pair;
    rb_journal_record rec;
    const rb_u8 *anchor;
    rb_u16 s, x, y;
    int state = open_disk(drive, pinned == 0, &ctx, &sources);
    if (state != SETTLED) { return state; }
    rb_journal_inspect(&pair, disk.slot[0], disk.slot[1], 3, &ctx, disk.live);
    if (!pair.status && pair.observation == RB_TX_COMMITTED_NEW
            && disk.slot[0][36] != disk.slot[1][36]) {
        a->tx.sequence = pair.record.sequence;
        a->tx.target = active_slot(disk.live);
        if (!matches_view(disk.live, a->tx.target)) { return BAD_JOURNAL; }
        if (pinned) {
            int finished = a->tx.sequence == pinned->sequence;
            if ((!finished && a->tx.sequence != pinned->sequence - 1)
                    || pair.source == pinned->prepare
                    || a->tx.target != (finished ? pinned->target : pinned->old)
                    || !matches_view(disk.slot[0] + 512, finished ? pinned->old : pinned->previous)) {
                return BAD_JOURNAL;
            }
        }
        return SETTLED;
    }
    for (s = 0; s < 2; ++s) {
        anchor = disk.slot[s];
        if (rb_journal_decode(&rec, anchor, RB_JOURNAL_BYTES, &ctx)) { continue; }
        if (rec.phase == RB_TX_COMMITTED && rec.sequence != 0xFFFFFFFFUL) {
            a->tx.sequence = rec.sequence + 1; a->tx.prepare = 1 - s;
            y = active_slot(anchor + 1024);
        } else if (rec.phase == RB_TX_PREPARED && rec.sequence >= 3
                && equal(anchor + 1024, shown.approved, 512)) {
            a->tx.sequence = rec.sequence; a->tx.prepare = s;
            y = active_slot(anchor + 512);
        } else { continue; }
        if (y == 4 || y == disk.target) { continue; }
        a->tx.old = y; a->tx.target = disk.target;
        for (x = 0; x < 4; ++x) {
            if (x == y || !(disk.mask & (1U << x))) { continue; }
            a->tx.previous = x;
            if (pinned && !equal((const rb_u8 *)pinned, (const rb_u8 *)&a->tx, sizeof(*pinned))) { continue; }
            if (!match(a, anchor)) { continue; }
            if (a->row == MBR && (pair.status || pair.source != a->tx.prepare
                    || pair.record.phase != RB_TX_PREPARED || pair.record.sequence != a->tx.sequence)) { return BAD_JOURNAL; }
            return a->mode;
        }
    }
    return BAD_JOURNAL;
}

static void show(const action *a)
{
    const transition *t = &a->tx;
    rb_u16 i;
    show_source(&shown.profile);
    print(RB_RS_PR_SEQUENCE); hex(t->sequence, 8); line("");
    print(RB_RS_PR_PROFILE); rb_putc('1' + (a->mode == UNDO ? t->old : t->target)); line("");
    line(a->mode == UNDO ? RB_RS_PR_UNDO : RB_RS_PR_FINISH);
    if (a->mode == FINISH && a->row <= MBR) {
        line(RB_RS_JR_DELTA);
        for (i = 0; i < 512; ++i) {
            if (disk.live[i] != shown.approved[i]) {
                print("0x"); hex(i, 4); print("     "); hex(disk.live[i], 2);
                print(" -> "); hex(shown.approved[i], 2); line("");
            }
        }
    }
    line(RB_RS_PR_SECTORS);
    i = a->row;
    for (;;) {
        print("0x"); hex(address(t, i), 8); line("");
        if (a->mode == UNDO) { if (!i) { break; } --i; }
        else if (++i == ROWS) { break; }
    }
    line(RB_RS_PR_CONFIRM);
}

static int apply(const action *a)
{
    rb_u8 actual[512];
    rb_u32 lba = address(&a->tx, a->row);
    if (!same_source() || !rb_ata_target_can_flush(&shown.profile)
            || !read_live(lba, actual) || !equal(actual, a->before, 512)) { return 0; }
    if (lba ? rb_ata_write_journal_sector(lba, a->after) : rb_ata_restore_mbr(a->after)) { return 0; }
    return same_source() && read_live(lba, actual) && equal(actual, a->after, 512);
}

rb_u16 __cdecl rb_profile_recovery_run(rb_u16 drive)
{
    action next;
    transition tx;
    rb_u8 reviewed[512], approved[512];
    int state, mode;
    rb_u16 row, key, expected_slot;
    shown.approved = approved;
    line("RB PROFILE RECOVERY"); line(RB_RS_RESTORE_CHECK);
    state = inspect(drive, &next, 0);
    if (state == SETTLED) { line(RB_RS_PR_IDLE); return 0; }
    if (state < UNDO) {
        line(state == BAD_BACKUP ? RB_RS_RESTORE_BACKUP : state == BAD_TARGET ? RB_RS_RESTORE_TARGET : RB_RS_PR_BAD);
        return 1;
    }
    tx = next.tx; row = next.row; mode = state; rb_store_copy(reviewed, next.before, 512);
    show(&next);
    do { key = rb_console_key(); } while (key != RB_RS_A_YES[0] && key != 27);
    if (key == 27) { line(RB_RS_RESTORE_CANCEL); return 0; }
    if (inspect(drive, &next, &tx) != mode || next.row != row || !equal(next.before, reviewed, 512)) {
        line(RB_RS_RESTORE_CHANGED); return 1;
    }
    for (;;) {
        if (!apply(&next)) { break; }
        state = inspect(drive, &next, &tx);
        if ((mode == UNDO && row == PRE_OLD) || row == END_HEADER) {
            expected_slot = mode == UNDO ? tx.old : tx.target;
            if (state == SETTLED && next.tx.target == expected_slot
                    && next.tx.sequence == tx.sequence - (mode == UNDO)) {
                line(mode == UNDO ? RB_RS_PR_UNDONE : RB_RS_JR_DONE); return 0;
            }
            break;
        }
        row = mode == UNDO ? row - 1 : row + 1;
        if (state != mode || next.row != row) { break; }
    }
    line(RB_RS_RESTORE_IO); return 1;
}
