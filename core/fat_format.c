/* Independently booted FAT16/FAT32 publication and rollback for one enrolled primary.
   The backup master is read-only. Publishing the VBR last gives each completed
   write (and each inverse write) an exact, recognizable on-disk state. */
#include "fat_review.h"
#include "fingerprint.h"
#include "config.h"
#include "mbr_compare.h"
#include "mbr_console.h"
#include "rescue_file.h"
#include "rescue_text.h"

#define TICKET_LBA 2873
/* Store only sectors that actually change. The offset is a 16-bit sector index. */
#define MAX_CHANGES 1024
typedef struct {
    rb_u8 magic[8];
    rb_u32 pair_crc, disk_id, start, length, metadata;
    rb_u16 slot, spc;
    rb_u32 original[2];
    rb_u16 heads, spt;
    rb_u8 reserved[464];
    rb_u32 crc;
} format_ticket;
typedef char ticket_sector[(sizeof(format_ticket) == 512) ? 1 : -1];

typedef struct { rb_u16 total, done; } progress;
typedef struct { rb_u16 offset; rb_u32 body, tail; } delta;

rb_u16 __cdecl rb_ata_format_write(rb_u32 first, rb_u32 last, rb_u32 lba, const rb_u8 *sector);
static format_ticket ticket;
static observation view;
static rb_u16 floppy, bits;
static const rb_u8 zero[512] = {0};
static rb_u8 original[512], desired[512], live[512];
static delta changes[MAX_CHANGES];

static int valid_ticket(void)
{
    return equal(ticket.magic, (const rb_u8 *)(bits == 16 ? "RBFMT161" : "RBFMT321"), 8)
        && rb_crc32((const rb_u8 *)&ticket, 508) == ticket.crc
        && equal(ticket.reserved, zero, sizeof(ticket.reserved))
        && ticket.pair_crc == rb_ide_pair_crc() && ticket.slot >= 1 && ticket.slot <= 4
        && ticket.start && ticket.metadata && ticket.metadata <= (bits == 16 ? 1024UL : 65535UL)
        && ticket.metadata <= ticket.length && ticket.start <= 0x0fffffffUL
        && ticket.metadata - 1 <= 0x0fffffffUL - ticket.start;
}

static void put16(rb_u8 *out, rb_u16 v)
{
    out[0] = (rb_u8)v; out[1] = (rb_u8)(v >> 8);
}

static void put32(rb_u8 *out, rb_u32 v)
{
    put16(out, (rb_u16)v); put16(out + 2, (rb_u16)(v >> 16));
}

static void field(rb_u8 *out, const char *s)
{
    while (*s) { *out++ = (rb_u8)*s++; }
}

static void boot_sector(void)
{
    rb_u16 drive_field, stub;
    desired[0] = 0xeb; desired[2] = 0x90;
    field(desired + 3, "RETROBT1"); put16(desired + 11, 512);
    desired[13] = (rb_u8)ticket.spc; put16(desired + 14, view.plan.reserved);
    desired[16] = 2; desired[21] = 0xf8;
    put16(desired + 24, ticket.spt); put16(desired + 26, ticket.heads);
    put32(desired + 28, ticket.start);
    if (bits == 16) {
        put16(desired + 17, 512);
        if (ticket.length <= 65535UL) { put16(desired + 19, (rb_u16)ticket.length); }
        else { put32(desired + 32, ticket.length); }
        put16(desired + 22, (rb_u16)view.plan.sectors_per_fat);
        drive_field = 36;
    } else {
        put32(desired + 32, ticket.length); put32(desired + 36, view.plan.sectors_per_fat);
        put32(desired + 44, 2); /* root cluster */
        put16(desired + 48, 1); put16(desired + 50, 6);
        drive_field = 64;
    }
    desired[drive_field] = 0x80; desired[drive_field + 2] = 0x29;
    put32(desired + drive_field + 3, ticket.disk_id ^ ticket.start);
    field(desired + drive_field + 7, "NO NAME    ");
    field(desired + drive_field + 18, bits == 16 ? "FAT16   " : "FAT32   ");
    stub = drive_field + 26;
    desired[1] = (rb_u8)(stub - 2);
    desired[stub] = 0xcd; desired[stub + 1] = 0x18; /* BIOS next boot device */
    desired[stub + 2] = 0xeb; desired[stub + 3] = 0xfe;
    put16(desired + 510, 0xaa55);
}

static void render(rb_u32 lba)
{
    rb_u32 offset = lba - ticket.start;
    clear(desired, 512);
    if (!offset || (bits == 32 && offset == 6)) {
        boot_sector();
    } else if (lba == view.plan.fat1 || lba == view.plan.fat2) {
        if (bits == 16) { put32(desired, 0xfffffff8UL); }
        else {
            put32(desired, 0x0ffffff8UL); put32(desired + 4, 0x0fffffffUL);
            put32(desired + 8, 0x0fffffffUL); /* cluster 2 belongs to the empty root */
        }
    } else if (bits == 32 && (offset == 1 || offset == 7)) {
        put32(desired, 0x41615252UL); put32(desired + 484, 0x61417272UL);
        put32(desired + 488, view.plan.clusters - 1); put32(desired + 492, 3);
        put32(desired + 508, 0xaa550000UL);
    } else if (bits == 32 && (offset == 2 || offset == 8)) {
        put16(desired + 510, 0xaa55); /* third sector of each FAT32 boot record */
    }
}

static const char *tables(rb_u32 digest[2])
{
    rb_format_comparison check;
    const char *error;
    if (rb_floppy_read(TICKET_LBA, live, &floppy) || !equal(live, (const rb_u8 *)&ticket, 512)) {
        return RB_RS_FW_TICKET;
    }
    if (rb_fat_observe(&view, ticket.slot, ticket.spc) || view.plan.bits != bits
        || view.plan.spc != ticket.spc || view.boot.lba != ticket.start
        || view.scan.entries[ticket.slot - 1].sectors != ticket.length
        || view.scan.disk_id != ticket.disk_id || rb_fat_metadata_last(&view.plan) - ticket.start + 1 != ticket.metadata
        || !ticket.heads || !ticket.spt || view.geometry[1] != ticket.heads || view.geometry[2] != ticket.spt) {
        return RB_RS_FW_LAYOUT;
    }
    clear((rb_u8 *)&check, sizeof(check));
    rb_fingerprint_sector(check.fingerprint, 0, view.mbr.bytes);
    error = rb_format_check_tables(&view, &check);
    if (error) { return error; }
    if (!rb_ide_can_flush()) { return RB_RS_FW_FLUSH; }
    digest[0] = check.fingerprint[0]; digest[1] = check.fingerprint[1];
    return 0;
}

static int same_digest(const rb_u32 a[2], const rb_u32 b[2])
{
    return a[0] == b[0] && a[1] == b[1];
}

static const char *read_pair(rb_u32 lba)
{
    if (rb_ata_copy_read(1, lba, original) || rb_ata_copy_read(0, lba, live)) { return RB_RS_FR_IO; }
    if (lba == ticket.start && (!equal(original, zero, 512) || !equal(live, view.boot.bytes, 512))) {
        return RB_RS_FW_FOREIGN;
    }
    if (bits == 32 && lba == ticket.start + 6 && !equal(original, zero, 512)) {
        return RB_RS_FW32_EXISTING;
    }
    render(lba);
    return 0;
}

static const char *inspect(progress *state, rb_u32 layout[2])
{
    rb_u16 offset;
    rb_u32 step;
    int foreign = 0;
    rb_u32 lba, digest[2], after[2];
    const char *error = tables(layout);
    if (error) { return error; }
    digest[0] = layout[0]; digest[1] = layout[1];
    state->done = state->total = 0;
    for (step = 1; step <= ticket.metadata; ++step) {
        /* FAT32 publishes the backup VBR immediately before the primary VBR. */
        if (step == ticket.metadata) { offset = 0; }
        else if (bits == 32 && step == ticket.metadata - 1) { offset = 6; }
        else { offset = (rb_u16)(step + (bits == 32 && step >= 6)); }
        lba = ticket.start + offset;
        error = read_pair(lba);
        if (error) { return error; }
        if (!equal(original, zero, 512)) { rb_fingerprint_sector(digest, lba, original); }
        if (equal(original, desired, 512)) {
            if (!equal(live, original, 512)) { foreign = 1; }
            continue;
        }
        if (state->total >= MAX_CHANGES) { return RB_RS_FW_LIMIT; }
        if (equal(live, desired, 512) && state->done == state->total) { ++state->done; }
        else if (!equal(live, original, 512)) { foreign = 1; }
        changes[state->total].offset = offset;
        changes[state->total].body = rb_crc32(original, 508);
        changes[state->total++].tail = rb_crc32(original + 508, 4);
    }
    if (!same_digest(digest, ticket.original)) { return RB_RS_FW_BACKUP; }
    if (foreign) { return RB_RS_FW_FOREIGN; }
    error = tables(after);
    if (error) { return error; }
    return same_digest(layout, after) ? 0 : RB_RS_FP_CHANGED;
}

static const char *apply(const progress *state, const rb_u32 layout[2], int restore)
{
    rb_u16 i, n = restore ? state->done : state->total;
    for (i = 0; i < n; ++i) {
        const delta *d = &changes[restore ? n - 1 - i : i];
        rb_u32 lba = ticket.start + d->offset, current[2];
        const rb_u8 *new_bytes = restore ? original : desired;
        const char *error = tables(current);
        if (error) { return error; }
        if (!same_digest(current, layout)) { return RB_RS_FP_CHANGED; }
        error = read_pair(lba);
        if (error) { return error; }
        if (rb_crc32(original, 508) != d->body || rb_crc32(original + 508, 4) != d->tail
            || !equal(live, restore ? desired : original, 512)) { return RB_RS_FW_FOREIGN; }
        if (rb_ata_format_write(ticket.start, ticket.start + ticket.metadata - 1, lba, new_bytes)
            || rb_ata_copy_read(0, lba, live) || !equal(live, new_bytes, 512)) { return RB_RS_FW_IO; }
    }
    return 0;
}

static rb_u16 blocked(const char *error)
{
    line(error);
    return 1;
}

static rb_u16 run(rb_u16 drive, rb_u16 family)
{
    progress shown, repeated;
    rb_u32 layout[2], again[2];
    rb_u16 key;
    int restore;
    const char *error;
    floppy = drive; bits = family;
    line(bits == 16 ? RB_RS_FW_TITLE : RB_RS_FW32_TITLE);
    if (rb_ide_load_pair(drive) != 1 || rb_floppy_read(TICKET_LBA, (rb_u8 *)&ticket, &floppy)
        || !valid_ticket()) { return blocked(RB_RS_FW_TICKET); }
    error = inspect(&shown, layout);
    if (error) { return blocked(error); }
    print(RB_RS_FP_TARGET); print(" P"); rb_putc('0' + ticket.slot); line("");
    rb_ide_print_pair();
    rb_fat_span(RB_RS_FR_SPAN, ticket.start, ticket.start + ticket.metadata - 1);
    count(RB_RS_FW_COUNT " ", shown.done); count(RB_RS_FW_TOTAL " ", shown.total);
    restore = shown.done != 0;
    if (shown.done == shown.total) { line(bits == 16 ? "RB FAT16 VERIFIED" : "RB FAT32 VERIFIED"); }
    else { line(restore ? RB_RS_FW_PARTIAL : RB_RS_FW_ORIGINAL); }
    line(restore ? RB_RS_FW_RESTORE : (bits == 16 ? RB_RS_FW_FORMAT : RB_RS_FW32_FORMAT));
    key = rb_console_key();
    if (key != (restore ? 'R' : 'F')) { line(RB_RS_FW_CANCEL); return 0; }
    line(RB_RS_FW_CONFIRM);
    if (rb_console_key() != '0' + ticket.slot) { line(RB_RS_FW_CANCEL); return 0; }
    error = inspect(&repeated, again);
    if (error) { return blocked(error); }
    if (!same_digest(layout, again) || repeated.total != shown.total || repeated.done != shown.done) {
        return blocked(RB_RS_FP_CHANGED);
    }
    line(restore ? RB_RS_FW_RESTORING : (bits == 16 ? RB_RS_FW_WRITING : RB_RS_FW32_WRITING));
    error = apply(&repeated, again, restore);
    if (error) { return blocked(error); }
    error = inspect(&repeated, again);
    if (error) { return blocked(error); }
    if (repeated.total != shown.total || repeated.done != (restore ? 0 : shown.total)) {
        return blocked(RB_RS_FW_IO);
    }
    if (restore) { line(bits == 16 ? "RB FAT16 RESTORE PASS" : "RB FAT32 RESTORE PASS"); }
    else { line(bits == 16 ? "RB FAT16 FORMAT PASS" : "RB FAT32 FORMAT PASS"); }
    return 0;
}

rb_u16 __cdecl rb_fat16_format_run(rb_u16 drive) { return run(drive, 16); }
rb_u16 __cdecl rb_fat32_format_run(rb_u16 drive) { return run(drive, 32); }
