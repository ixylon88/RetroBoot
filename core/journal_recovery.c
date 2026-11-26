/* Complete the first prepared visibility change on the enrolled disk. */
#include "restore_target.h"
#include "backup_target.h"
#include "dos_scope.h"
#include "journal.h"
#include "restore_stage1.h"

rb_u16 __cdecl rb_ata_write_journal_sector(rb_u32 lba, const rb_u8 *sector);
rb_u16 __cdecl rb_ata_restore_mbr(const rb_u8 *sector);

enum { BAD_BACKUP, BAD_TARGET, BAD_JOURNAL, CHANGED, NEED_DISCARD, NEED_PREPARE, NEED_MBR, NEED_SNAPSHOT, NEED_HEADER, COMPLETE, BASELINE };
enum { SHOW, CONFIRM, AFTER_PREPARE, AFTER_MBR, AFTER_SNAPSHOT, AFTER_HEADER, AFTER_DISCARD };
enum { HEADER_SECTOR = 0, NEW_SECTOR = 2, LIVE_MBR = 3 };

static rb_u8 records[2][RB_JOURNAL_BYTES];
static struct {
    rb_ata_enrollment profile;
    rb_u32 lba[2][3];
    rb_u16 dest;
    /* The immutable Stage 1 prefix is verified on every acquisition. */
    rb_u8 approved_tail[512 - sizeof(stage1_code)];
} shown;

typedef struct {
    rb_u8 mbr[512], prepare_header[512], header[512], snapshot[512];
    /* Both validated headers have zero padding and deterministic trailing CRCs. */
    rb_u8 publication[STORE_COMMIT_FIELDS], prepare_fields[RB_JOURNAL_HEADER_FIELDS];
    /* A decoded visibility change preserves every old byte outside the primary table. */
    rb_u8 old_table[64];
} recovery_preimage;

static void store_crc(rb_u8 *out, const rb_u8 *data, rb_u16 bytes)
{
    rb_u32 crc = rb_crc32(data, bytes);
    rb_u16 i;
    for (i = 0; i < 4; ++i) { out[i] = (rb_u8)crc; crc >>= 8; }
}

/* A partially written sector must be an exact new prefix and old suffix. */
static int prefix_write(const rb_u8 *actual, const rb_u8 *next, const rb_u8 *old)
{
    rb_u16 i = 0;
    while (i < 512 && actual[i] == next[i]) { ++i; }
    return equal(actual + i, old + i, 512 - i);
}

static int recheck_live(int state, const rb_u8 *live, rb_u8 *scratch)
{
    return same_source() && read_live(0, scratch) && equal(scratch, live, 512) ? state : BAD_TARGET;
}

static int classify(const rb_u8 *current, const rb_u8 *prepared, rb_u8 *done, rb_u8 *seed)
{
    const rb_u8 *old = prepared + 512, *next = prepared + 1024;
    if (!equal(current + 512, old, 512)) { return BAD_JOURNAL; }

    /* Sequence 1 stored this exact before-image twice. Its header must still
       be intact if the new snapshot in the completion slot is unfinished. */
    rb_store_copy(seed, prepared, 512);
    seed[16] = 1; seed[36] = RB_TX_EMPTY;
    rb_store_copy(seed + 68, seed + 64, 4);
    store_crc(seed + 508, seed, 508);

    rb_store_copy(done, prepared, 512);
    done[36] = RB_TX_COMMITTED;
    store_crc(done + 508, done, 508);
    if (!equal(current + 1024, next, 512)) {
        if (equal(current, seed, 512) && prefix_write(current + 1024, next, old)) { return NEED_SNAPSHOT; }
        return BAD_JOURNAL;
    }
    if (equal(current, done, 512)) { return COMPLETE; }
    return prefix_write(current, done, seed) ? NEED_HEADER : BAD_JOURNAL;
}

static int pin(rb_u8 *field, const rb_u8 *value, rb_u16 size, int step)
{
    if (step == SHOW) { rb_store_copy(field, value, size); return 1; }
    return equal(field, value, size);
}

/* With an intact baseline, both snapshots and the old live MBR determine a
   single proposed prepare. The journal decoder still has to accept the pair. */
static int recover_prepare_header(rb_u8 *candidate, const rb_u8 *seed, const rb_u8 *live,
                                  const rb_u8 *approved, rb_u8 *header)
{
    if (!equal(live, seed + 512, 512) || equal(live, approved, 512)) { return 0; }
    rb_store_copy(header, seed, 512);
    header[16] = 2; header[36] = RB_TX_PREPARED;
    store_crc(header + 68, approved, 512);
    store_crc(header + 508, header, 508);
    if (!prefix_write(candidate, header, seed)) { return 0; }
    rb_store_copy(candidate, header, 512);
    return 1;
}

static int inspect(rb_u16 drive, int step, recovery_preimage *before)
{
    const rb_backup *saved;
    const rb_u8 *approved = rb_store.witness.approved;
    rb_backup_sources sources;
    rb_backup_target target;
    rb_journal_context ctx;
    rb_journal_record record;
    rb_journal_result result;
    rb_u8 live[512], done[512], scratch[512], *prepared, *current;
    rb_u16 i, j, dest, source = RB_JOURNAL_NONE, baseline = RB_JOURNAL_NONE;
    int state, incomplete, discard;

    if (rb_store_open(drive) != RB_STORE_OCCUPIED || !(saved = rb_store_verify())) { return BAD_BACKUP; }
    if (!rb_store_probe_source() || !rb_ata_target_can_flush(&rb_store.profile)
        || !mbr_only(saved, scratch) || !read_live(0, live)
        || !equal(approved, stage1_code, sizeof(stage1_code))) { return BAD_TARGET; }
    rb_backup_match_selected_sources(&target, &sources, saved, &rb_store.source.device, rb_store.source.read, 0, rb_dos_recovery_slots);
    if (target.status) { return BAD_TARGET; }
    if (!pin((rb_u8 *)&shown.profile, (const rb_u8 *)&rb_store.profile, sizeof(shown.profile), step)
        || !pin((rb_u8 *)shown.lba, (const rb_u8 *)sources.journal_lba, sizeof(shown.lba), step)
        || !pin(before->publication, rb_store.metadata, sizeof(before->publication), step)
        || !pin(shown.approved_tail, approved + sizeof(stage1_code), sizeof(shown.approved_tail), step)) { return CHANGED; }
    ctx.scan = &sources.scan;
    for (i = 4; i < sources.scan.count && sources.scan.entries[i].start != target.admin_start; ++i) {}
    ctx.admin_index = i;
    ctx.capacity_low = saved->capacity_low; ctx.capacity_high = saved->capacity_high;
    ctx.io_mode = 1; ctx.heads = ctx.sectors_per_track = 0;
    rb_store_copy(ctx.media_id, target.media_id, 16);
    for (i = 0; i < 2; ++i) {
        for (j = 0; j < 3; ++j) {
            if (!read_live(sources.journal_lba[i][j], records[i] + 512 * j)) { return BAD_JOURNAL; }
        }
        if (rb_journal_decode(&record, records[i], RB_JOURNAL_BYTES, &ctx)) { continue; }
        if (record.phase == RB_TX_EMPTY) { baseline = i; }
        if (record.phase == RB_TX_PREPARED && record.sequence == 2) {
            if (source != RB_JOURNAL_NONE) { return BAD_JOURNAL; }
            source = i;
        }
    }
    incomplete = source == RB_JOURNAL_NONE;
    if (incomplete) {
        if (baseline == RB_JOURNAL_NONE) { return BAD_JOURNAL; }
        if (equal(records[0], records[1], RB_JOURNAL_BYTES)) {
            /* Both slots are the same decoded baseline, including both full MBRs. */
            if (!equal(live, records[baseline] + 512, 512)) { return BAD_JOURNAL; }
            if (step == AFTER_DISCARD && (!equal(live, before->mbr, 512)
                    || !equal(records[baseline], before->header, 512))) { return CHANGED; }
            return recheck_live(BASELINE, live, scratch);
        }
        if (step > CONFIRM) { return BAD_JOURNAL; }
        source = 1 - baseline;
    }
    dest = 1 - source; prepared = records[source]; current = records[dest];
    discard = !equal(prepared + 1024, approved, 512);
    if (discard) {
        if (!incomplete || !equal(prepared, current, 1024)
                || !rb_journal_unfinished_snapshot(prepared + 1024, approved, current + 512)) { return BAD_JOURNAL; }
        if (!pin(before->snapshot, prepared + 1024, 512, step)) { return CHANGED; }
        /* Supply the independently approved sector to the decoder in RAM only. */
        rb_store_copy(prepared + 1024, approved, 512);
    }
    if (step <= CONFIRM && !pin(before->prepare_header, prepared, 512, step)) { return CHANGED; }
    if (incomplete && !recover_prepare_header(prepared, current, live, approved, scratch)) {
        return BAD_JOURNAL;
    }
    state = classify(current, prepared, done, scratch);
    if (state == BAD_JOURNAL) { return state; }
    if (!equal(live, approved, 512)) {
        /* Only an old MBR or an exact new prefix followed by its old suffix
           is eligible. The validated prepare permits only visibility bytes. */
        if (!prefix_write(live, approved, prepared + 512)) { return BAD_TARGET; }
        rb_journal_inspect(&result, records[0], records[1], 3, &ctx, live);
        /* Selecting this unique sequence-2 prepare requires an intact baseline
           peer. A committed, damaged or advanced peer cannot authorize LBA 0. */
        if (result.status || result.source != source) { return BAD_JOURNAL; }
        state = incomplete ? NEED_PREPARE : NEED_MBR;
    }

    if (step == SHOW) { shown.dest = dest; }
    if (shown.dest != dest || !pin(before->prepare_fields, prepared, sizeof(before->prepare_fields), step)
        || !pin(before->old_table, prepared + 512 + 446, sizeof(before->old_table), step)) { return CHANGED; }
    if (step <= AFTER_PREPARE && !pin(before->mbr, live, 512, step)) { return CHANGED; }
    if (step != AFTER_HEADER && !pin(before->header, current, 512, step)) { return CHANGED; }
    if (discard) {
        /* Restore only the unpublished copy, using the intact peer's old MBR. */
        rb_store_copy(prepared + 1024, current + 512, 512);
        return recheck_live(NEED_DISCARD, live, scratch);
    }
    if (step <= AFTER_MBR && !pin(before->snapshot, current + 1024, 512, step)) { return CHANGED; }
    if ((step == AFTER_PREPARE && state != NEED_MBR) || (step == AFTER_MBR && state != NEED_SNAPSHOT)
            || (step == AFTER_SNAPSHOT && state != NEED_HEADER)
            || (step == AFTER_HEADER && state != COMPLETE)) {
        return CHANGED;
    }

    /* Validate the proposed final pair before a write. In the final check
       classify() already proved that these bytes are physically present. */
    rb_store_copy(current + 1024, approved, 512);
    rb_store_copy(current, done, 512);
    rb_journal_inspect(&result, records[0], records[1], 3, &ctx, approved);
    if (result.status || result.source != dest || result.observation != RB_TX_COMMITTED_NEW) { return BAD_JOURNAL; }
    if (!sources.dos_slots || (result.record.changed & ~sources.dos_slots)
            || (sources.profile_count > 1 && rb_dos_view_slot(approved, sources.dos_slots) == 4)) {
        return BAD_TARGET;
    }
    return recheck_live(state, live, scratch);
}

static void hex_digits(rb_u32 value, rb_u16 digits)
{
    static const char hex[] = "0123456789ABCDEF";
    while (digits) { --digits; rb_putc(hex[(value >> (digits * 4)) & 15]); }
}

static void show_mbr(const rb_u8 *live)
{
    /* inspect matched this complete snapshot to the independently pinned MBR. */
    const rb_u8 *next = records[1 - shown.dest] + 1024;
    rb_u16 i;
    line(RB_RS_JR_MBR); line(RB_RS_JR_DELTA);
    for (i = 0; i < 512; ++i) {
        if (live[i] != next[i]) {
            print("0x"); hex_digits(i, 4); print("     "); hex_digits(live[i], 2);
            print(" -> "); hex_digits(next[i], 2); line("");
        }
    }
}

static void show_sector(const char *label, rb_u16 slot, rb_u16 index)
{
    print(label); print(slot ? " RBTXN.B, LBA 0x" : " RBTXN.A, LBA 0x");
    hex_digits(shown.lba[slot][index], 8); line("");
}

static int write_checked(rb_u16 slot, rb_u16 index, const rb_u8 *before)
{
    rb_u8 sector[512];
    rb_u32 lba = index == LIVE_MBR ? 0 : shown.lba[slot][index];
    const rb_u8 *next = index == LIVE_MBR ? records[1 - shown.dest] + 1024 : records[slot] + 512 * index;
    if (!rb_ata_target_can_flush(&shown.profile) || !read_live(lba, sector) || !equal(sector, before, 512)) { return 0; }
    if (index == LIVE_MBR ? rb_ata_restore_mbr(next) : rb_ata_write_journal_sector(lba, next)) { return 0; }
    return same_source() && read_live(lba, sector) && equal(sector, next, 512);
}

static void show_plan(int state, const rb_u8 *live, rb_u16 dest)
{
    show_source(&shown.profile);
    if (state == NEED_DISCARD) {
        line(RB_RS_JR_UNFINISHED);
        show_sector(RB_RS_JR_SNAPSHOT, 1 - dest, NEW_SECTOR);
        line(RB_RS_JR_DISCARD);
        return;
    }
    if (state == NEED_PREPARE || state == NEED_MBR) {
        if (state == NEED_PREPARE) {
            line(RB_RS_JR_INCOMPLETE);
            show_sector(RB_RS_JR_PREPARE_HEADER, 1 - dest, HEADER_SECTOR);
        } else { line(equal(live, records[1 - dest] + 512, 512) ? RB_RS_JR_PREPARED : RB_RS_JR_PARTIAL); }
        show_mbr(live);
    } else { line(RB_RS_JR_SCOPE); }
    if (state != NEED_HEADER) { show_sector(RB_RS_JR_SNAPSHOT, dest, NEW_SECTOR); }
    show_sector(RB_RS_JR_HEADER, dest, HEADER_SECTOR);
    line(state == NEED_PREPARE ? RB_RS_JR_PREPARE_APPLY : state == NEED_MBR ? RB_RS_JR_APPLY
        : state == NEED_SNAPSHOT ? RB_RS_JR_CONFIRM_BOTH : RB_RS_JR_CONFIRM);
}

rb_u16 __cdecl rb_journal_recovery_run(rb_u16 drive)
{
    recovery_preimage before;
    int state;
    rb_u16 key, dest;
    line("RB JOURNAL RECOVERY"); line(RB_RS_RESTORE_CHECK);
    state = inspect(drive, SHOW, &before);
    if (state == COMPLETE || state == BASELINE) {
        line(state == BASELINE ? RB_RS_JR_BASELINE : RB_RS_JR_INTACT); return 0;
    }
    if (state < NEED_DISCARD || state > NEED_HEADER) {
        line(state == BAD_BACKUP ? RB_RS_RESTORE_BACKUP : state == BAD_TARGET ? RB_RS_RESTORE_TARGET : RB_RS_JR_BAD);
        return 1;
    }
    dest = shown.dest;
    show_plan(state, before.mbr, dest);
    do { key = rb_console_key(); } while (key != RB_RS_A_YES[0] && key != 27);
    if (key == 27) { line(RB_RS_RESTORE_CANCEL); return 0; }
    if (inspect(drive, CONFIRM, &before) != state) { line(RB_RS_RESTORE_CHANGED); return 1; }

    if (state == NEED_DISCARD) {
        if (!write_checked(1 - dest, NEW_SECTOR, before.snapshot)
                || inspect(drive, AFTER_DISCARD, &before) != BASELINE) {
            line(RB_RS_RESTORE_IO); return 1;
        }
        line(RB_RS_JR_DISCARDED); return 0;
    }
    if (state == NEED_PREPARE) {
        if (!write_checked(1 - dest, HEADER_SECTOR, before.prepare_header)
                || inspect(drive, AFTER_PREPARE, &before) != NEED_MBR) {
            line(RB_RS_RESTORE_IO); return 1;
        }
        line(RB_RS_JR_PREPARE_DONE);
        state = NEED_MBR;
    }
    if (state == NEED_MBR) {
        if (!write_checked(dest, LIVE_MBR, before.mbr) || inspect(drive, AFTER_MBR, &before) != NEED_SNAPSHOT) {
            line(RB_RS_RESTORE_IO); return 1;
        }
        line(RB_RS_JR_MBR_DONE);
        state = NEED_SNAPSHOT;
    }
    if (state == NEED_SNAPSHOT) {
        if (!write_checked(dest, NEW_SECTOR, before.snapshot) || inspect(drive, AFTER_SNAPSHOT, &before) != NEED_HEADER) {
            line(RB_RS_RESTORE_IO); return 1;
        }
        line(RB_RS_JR_SNAPSHOT_DONE);
    }
    if (!write_checked(dest, HEADER_SECTOR, before.header) || inspect(drive, AFTER_HEADER, &before) != COMPLETE) {
        line(RB_RS_RESTORE_IO); return 1;
    }
    line(RB_RS_JR_DONE); return 0;
}
