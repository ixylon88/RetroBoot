/* Complete the first visibility change after both snapshots reached disk. */
#include "restore_target.h"
#include "backup_target.h"
#include "journal.h"
#include "restore_stage1.h"

rb_u16 __cdecl rb_ata_write_journal_header(rb_u32 lba, const rb_u8 *sector);

enum { BAD_BACKUP, BAD_TARGET, BAD_JOURNAL, CHANGED, READY, COMPLETE };
enum { SHOW, CONFIRM, READBACK };

static rb_backup_sources sources;
static rb_u8 records[2][RB_JOURNAL_BYTES], scratch[512];
/* Pin every byte that defines the operator's decision across the keypress. */
static struct {
    rb_ata_enrollment profile;
    rb_u32 lba[2][3];
    rb_u16 dest;
    rb_u8 publication[512], prepared[RB_JOURNAL_BYTES], previous[512];
} shown;

static void seal_header(rb_u8 *h)
{
    rb_u32 crc = rb_crc32(h, 508);
    rb_u16 i;
    for (i = 0; i < 4; ++i) { h[508 + i] = (rb_u8)crc; crc >>= 8; }
}

/* The possible old header is unique for sequence 2: the empty baseline
   described this exact before-image twice. A prefix of the exact completion
   followed by its exact baseline suffix is also safe to finish after a tear. */
static int expected_header(const rb_u8 *current, const rb_u8 *done, const rb_u8 *prepared)
{
    rb_u16 i = 0;
    rb_store_copy(scratch, prepared, 512);
    scratch[16] = 1;
    scratch[36] = RB_TX_EMPTY;
    rb_store_copy(scratch + 68, scratch + 64, 4);
    seal_header(scratch);
    while (i < 512 && current[i] == done[i]) { ++i; }
    return equal(current + i, scratch + i, 512 - i);
}

static int pin(rb_u8 *field, const rb_u8 *value, rb_u16 size, int step)
{
    if (step == SHOW) { rb_store_copy(field, value, size); return 1; }
    return equal(field, value, size);
}

static int inspect(rb_u16 drive, int step)
{
    const rb_backup *saved;
    const rb_u8 *approved = rb_store.witness.approved;
    rb_backup_target target;
    rb_journal_context ctx;
    rb_journal_record record;
    rb_journal_result result;
    rb_u8 done[512], *prepared, *current;
    rb_u16 i, j, dest, source = RB_JOURNAL_NONE;
    int complete;

    if (rb_store_open(drive) != RB_STORE_OCCUPIED || !(saved = rb_store_verify())) { return BAD_BACKUP; }
    if (!rb_store_probe_source() || !rb_ata_target_can_flush(&rb_store.profile)
        || !mbr_only(saved, scratch) || !read_live(0, scratch)
        || !equal(scratch, approved, 512) || !equal(approved, stage1_code, sizeof(stage1_code))) { return BAD_TARGET; }
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
    if (!equal(prepared + 1024, approved, 512) || !equal(prepared + 512, current + 512, 1024)) { return BAD_JOURNAL; }
    rb_store_copy(done, prepared, 512);
    done[36] = RB_TX_COMMITTED;
    seal_header(done);
    complete = equal(current, done, 512);
    if (!complete && !expected_header(current, done, prepared)) { return BAD_JOURNAL; }

    if (step == SHOW) { shown.dest = dest; }
    if (shown.dest != dest || !pin((rb_u8 *)&shown.profile, (const rb_u8 *)&rb_store.profile, sizeof(shown.profile), step)
        || !pin((rb_u8 *)shown.lba, (const rb_u8 *)sources.journal_lba, sizeof(shown.lba), step)
        || !pin(shown.publication, rb_store.metadata, 512, step) || !pin(shown.prepared, prepared, RB_JOURNAL_BYTES, step)
        || (step != READBACK && !pin(shown.previous, current, 512, step))) { return CHANGED; }

    /* Project the one proposed sector in memory and use the ordinary journal
       selector. During readback the on-disk header itself must be complete. */
    if (step == READBACK && !complete) { return BAD_JOURNAL; }
    rb_store_copy(current, done, 512);
    rb_journal_inspect(&result, records[0], records[1], 3, &ctx, approved);
    if (result.status || result.source != dest || result.observation != RB_TX_COMMITTED_NEW) { return BAD_JOURNAL; }
    if (!same_source() || !read_live(0, scratch) || !equal(scratch, approved, 512)) { return BAD_TARGET; }
    return complete ? COMPLETE : READY;
}

static void show_header(void)
{
    static const char hex[] = "0123456789ABCDEF";
    rb_u32 lba = shown.lba[shown.dest][0];
    int shift;
    print(RB_RS_JR_HEADER); print(shown.dest ? " RBTXN.B, LBA 0x" : " RBTXN.A, LBA 0x");
    for (shift = 28; shift >= 0; shift -= 4) { rb_putc(hex[(lba >> shift) & 15]); }
    line("");
}

rb_u16 __cdecl rb_journal_recovery_run(rb_u16 drive)
{
    int status;
    rb_u16 key;
    rb_u32 lba;
    line("RB JOURNAL RECOVERY"); line(RB_RS_RESTORE_CHECK);
    status = inspect(drive, SHOW);
    if (status == COMPLETE) { line(RB_RS_JR_INTACT); return 0; }
    if (status != READY) {
        line(status == BAD_BACKUP ? RB_RS_RESTORE_BACKUP : status == BAD_TARGET ? RB_RS_RESTORE_TARGET : RB_RS_JR_BAD);
        return 1;
    }
    show_source(&shown.profile); line(RB_RS_JR_SCOPE); show_header(); line(RB_RS_JR_CONFIRM);
    do { key = rb_console_key(); } while (key != RB_RS_A_YES[0] && key != 27);
    if (key == 27) { line(RB_RS_RESTORE_CANCEL); return 0; }
    status = inspect(drive, CONFIRM);
    lba = shown.lba[shown.dest][0];
    if (status != READY || !rb_ata_target_can_flush(&shown.profile)
            || !read_live(lba, scratch) || !equal(scratch, shown.previous, 512)) {
        line(RB_RS_RESTORE_CHANGED); return 1;
    }
    if (rb_ata_write_journal_header(lba, records[shown.dest]) || !same_source()
            || !read_live(lba, scratch) || !equal(scratch, records[shown.dest], 512)
            || inspect(drive, READBACK) != COMPLETE) { line(RB_RS_RESTORE_IO); return 1; }
    line(RB_RS_JR_DONE); return 0;
}
