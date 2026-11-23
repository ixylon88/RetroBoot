/* Complete the first prepared visibility change on the enrolled disk. */
#include "restore_target.h"
#include "backup_target.h"
#include "journal.h"
#include "restore_stage1.h"

rb_u16 __cdecl rb_ata_write_journal_sector(rb_u32 lba, const rb_u8 *sector);
rb_u16 __cdecl rb_ata_restore_mbr(const rb_u8 *sector);

enum { BAD_BACKUP, BAD_TARGET, BAD_JOURNAL, CHANGED, NEED_MBR, NEED_SNAPSHOT, NEED_HEADER, COMPLETE };
enum { SHOW, CONFIRM, AFTER_MBR, AFTER_SNAPSHOT, AFTER_HEADER };
enum { HEADER_SECTOR = 0, NEW_SECTOR = 2, LIVE_MBR = 3 };

static rb_u8 records[2][RB_JOURNAL_BYTES];
static struct {
    rb_ata_enrollment profile;
    rb_u32 lba[2][3];
    rb_u16 dest;
    rb_u8 publication[512], prepared[RB_JOURNAL_BYTES];
} shown;

typedef struct {
    rb_u8 header[512], snapshot[512];
} journal_preimage;

static void seal_header(rb_u8 *h)
{
    rb_u32 crc = rb_crc32(h, 508);
    rb_u16 i;
    for (i = 0; i < 4; ++i) { h[508 + i] = (rb_u8)crc; crc >>= 8; }
}

/* A partially written sector must be an exact new prefix and old suffix. */
static int prefix_write(const rb_u8 *actual, const rb_u8 *next, const rb_u8 *old)
{
    rb_u16 i = 0;
    while (i < 512 && actual[i] == next[i]) { ++i; }
    return equal(actual + i, old + i, 512 - i);
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
    seal_header(seed);

    rb_store_copy(done, prepared, 512);
    done[36] = RB_TX_COMMITTED;
    seal_header(done);
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

static int inspect(rb_u16 drive, int step, journal_preimage *before)
{
    const rb_backup *saved;
    const rb_u8 *approved = rb_store.witness.approved;
    rb_backup_sources sources;
    rb_backup_target target;
    rb_journal_context ctx;
    rb_journal_record record;
    rb_journal_result result;
    rb_u8 live[512], done[512], scratch[512], *prepared, *current;
    rb_u16 i, j, dest, source = RB_JOURNAL_NONE;
    int state;

    if (rb_store_open(drive) != RB_STORE_OCCUPIED || !(saved = rb_store_verify())) { return BAD_BACKUP; }
    if (!rb_store_probe_source() || !rb_ata_target_can_flush(&rb_store.profile)
        || !mbr_only(saved, scratch) || !read_live(0, live)
        || !equal(approved, stage1_code, sizeof(stage1_code))) { return BAD_TARGET; }
    rb_backup_match_sources(&target, &sources, saved, &rb_store.source.device, rb_store.source.read, (void *)0);
    if (target.status) { return BAD_TARGET; }
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
        if (!rb_journal_decode(&record, records[i], RB_JOURNAL_BYTES, &ctx)
                && record.phase == RB_TX_PREPARED && record.sequence == 2) {
            if (source != RB_JOURNAL_NONE) { return BAD_JOURNAL; }
            source = i;
        }
    }
    if (source == RB_JOURNAL_NONE) { return BAD_JOURNAL; }
    dest = 1 - source; prepared = records[source]; current = records[dest];
    if (!equal(prepared + 1024, approved, 512)) { return BAD_JOURNAL; }
    state = classify(current, prepared, done, scratch);
    if (state == BAD_JOURNAL) { return state; }
    if (!equal(live, approved, 512)) {
        if (!equal(live, prepared + 512, 512)) { return BAD_TARGET; }
        /* Only a fully valid baseline/prepare pair can authorize LBA 0.
           The decoder restricts every changed byte to primary type/active flags. */
        rb_journal_inspect(&result, records[0], records[1], 3, &ctx, live);
        if (result.status || result.source != source || result.observation != RB_TX_PREPARED_OLD) { return BAD_JOURNAL; }
        state = NEED_MBR;
    }

    if (step == SHOW) { shown.dest = dest; }
    if (shown.dest != dest || !pin((rb_u8 *)&shown.profile, (const rb_u8 *)&rb_store.profile, sizeof(shown.profile), step)
        || !pin((rb_u8 *)shown.lba, (const rb_u8 *)sources.journal_lba, sizeof(shown.lba), step)
        || !pin(shown.publication, rb_store.metadata, 512, step) || !pin(shown.prepared, prepared, RB_JOURNAL_BYTES, step)) {
        return CHANGED;
    }
    if (step != AFTER_HEADER && !pin(before->header, current, 512, step)) { return CHANGED; }
    if (step <= AFTER_MBR && !pin(before->snapshot, current + 1024, 512, step)) { return CHANGED; }
    if ((step == AFTER_MBR && state != NEED_SNAPSHOT) || (step == AFTER_SNAPSHOT && state != NEED_HEADER)
            || (step == AFTER_HEADER && state != COMPLETE)) {
        return CHANGED;
    }

    /* Validate the proposed final pair before a write. In the final check
       classify() already proved that these bytes are physically present. */
    rb_store_copy(current + 1024, approved, 512);
    rb_store_copy(current, done, 512);
    rb_journal_inspect(&result, records[0], records[1], 3, &ctx, approved);
    if (result.status || result.source != dest || result.observation != RB_TX_COMMITTED_NEW) { return BAD_JOURNAL; }
    if (!same_source() || !read_live(0, scratch) || !equal(scratch, live, 512)) { return BAD_TARGET; }
    return state;
}

static void hex_digits(rb_u32 value, rb_u16 digits)
{
    static const char hex[] = "0123456789ABCDEF";
    while (digits) { --digits; rb_putc(hex[(value >> (digits * 4)) & 15]); }
}

static void show_mbr(void)
{
    const rb_u8 *old = shown.prepared + 512, *next = old + 512;
    rb_u16 i;
    line(RB_RS_JR_MBR); line(RB_RS_JR_DELTA);
    for (i = 0; i < 512; ++i) {
        if (old[i] != next[i]) {
            print("0x"); hex_digits(i, 4); print("     "); hex_digits(old[i], 2);
            print(" -> "); hex_digits(next[i], 2); line("");
        }
    }
}

static void show_sector(const char *label, rb_u16 index)
{
    print(label); print(shown.dest ? " RBTXN.B, LBA 0x" : " RBTXN.A, LBA 0x");
    hex_digits(shown.lba[shown.dest][index], 8); line("");
}

static int write_checked(rb_u16 index, const rb_u8 *before)
{
    rb_u8 sector[512];
    rb_u32 lba = index == LIVE_MBR ? 0 : shown.lba[shown.dest][index];
    const rb_u8 *next = index == LIVE_MBR ? shown.prepared + 1024 : records[shown.dest] + 512 * index;
    if (!rb_ata_target_can_flush(&shown.profile) || !read_live(lba, sector) || !equal(sector, before, 512)) { return 0; }
    if (index == LIVE_MBR ? rb_ata_restore_mbr(next) : rb_ata_write_journal_sector(lba, next)) { return 0; }
    return same_source() && read_live(lba, sector) && equal(sector, next, 512);
}

rb_u16 __cdecl rb_journal_recovery_run(rb_u16 drive)
{
    journal_preimage before;
    int state;
    rb_u16 key;
    line("RB JOURNAL RECOVERY"); line(RB_RS_RESTORE_CHECK);
    state = inspect(drive, SHOW, &before);
    if (state == COMPLETE) { line(RB_RS_JR_INTACT); return 0; }
    if (state != NEED_MBR && state != NEED_HEADER && state != NEED_SNAPSHOT) {
        line(state == BAD_BACKUP ? RB_RS_RESTORE_BACKUP : state == BAD_TARGET ? RB_RS_RESTORE_TARGET : RB_RS_JR_BAD);
        return 1;
    }
    show_source(&shown.profile); line(state == NEED_MBR ? RB_RS_JR_PREPARED : RB_RS_JR_SCOPE);
    if (state == NEED_MBR) { show_mbr(); }
    if (state != NEED_HEADER) { show_sector(RB_RS_JR_SNAPSHOT, NEW_SECTOR); }
    show_sector(RB_RS_JR_HEADER, HEADER_SECTOR);
    line(state == NEED_MBR ? RB_RS_JR_APPLY : state == NEED_SNAPSHOT ? RB_RS_JR_CONFIRM_BOTH : RB_RS_JR_CONFIRM);
    do { key = rb_console_key(); } while (key != RB_RS_A_YES[0] && key != 27);
    if (key == 27) { line(RB_RS_RESTORE_CANCEL); return 0; }
    if (inspect(drive, CONFIRM, &before) != state) { line(RB_RS_RESTORE_CHANGED); return 1; }

    if (state == NEED_MBR) {
        if (!write_checked(LIVE_MBR, shown.prepared + 512) || inspect(drive, AFTER_MBR, &before) != NEED_SNAPSHOT) {
            line(RB_RS_RESTORE_IO); return 1;
        }
        line(RB_RS_JR_MBR_DONE);
        state = NEED_SNAPSHOT;
    }
    if (state == NEED_SNAPSHOT) {
        if (!write_checked(NEW_SECTOR, before.snapshot) || inspect(drive, AFTER_SNAPSHOT, &before) != NEED_HEADER) {
            line(RB_RS_RESTORE_IO); return 1;
        }
        line(RB_RS_JR_SNAPSHOT_DONE);
    }
    if (!write_checked(HEADER_SECTOR, before.header) || inspect(drive, AFTER_HEADER, &before) != COMPLETE) {
        line(RB_RS_RESTORE_IO); return 1;
    }
    line(RB_RS_JR_DONE); return 0;
}
