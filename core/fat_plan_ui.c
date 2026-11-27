/* Read-only installer preview on an independently booted rescue floppy. */
#include "fat_review.h"
#include "volume.h"
#include "mbr_console.h"
#include "mbr_compare.h"
#include "rescue_text.h"

enum { NO_DEVICE = RB_FORMAT_CLUSTER_COUNT + 1, BAD_TABLE, READ_ERROR, CHANGED };
static observation first, second;

static rb_u16 __cdecl cached_read(rb_u32 lba, rb_u8 *sector, void *opaque)
{
    const sector_copy *saved = opaque;
    rb_u16 i;
    if (lba != saved->lba) { return rb_disk_read(lba, sector, 0); }
    for (i = 0; i < 512; ++i) { sector[i] = saved->bytes[i]; }
    return 0;
}

static rb_u16 observe(observation *s, rb_u16 slot, rb_u16 spc)
{
    rb_u16 status;
    rb_u32 id;
    const rb_u8 *mbr = s->mbr.bytes;
    const rb_partition *p;
    if (rb_rescue_probe(&s->disk)) { return NO_DEVICE; }
    rb_dos_geometry(s->geometry);
    s->mbr.lba = 0;
    if (rb_disk_read(0, s->mbr.bytes, 0)) { return READ_ERROR; }
    id = (rb_u32)mbr[440] | ((rb_u32)mbr[441] << 8) | ((rb_u32)mbr[442] << 16) | ((rb_u32)mbr[443] << 24);
    if (rb_scan_partitions(&s->scan, cached_read, &s->mbr, s->disk.capacity_low, s->disk.capacity_high, id)) {
        return s->scan.status == RB_SCAN_IO ? READ_ERROR : BAD_TABLE;
    }
    p = &s->scan.entries[slot - 1];
    status = rb_plan_primary_fat(&s->plan, p, mbr + 446 + (slot - 1) * 16,
                                 &s->disk, s->geometry, spc);
    if (status) { return status; }
    s->boot.lba = p->start;
    return rb_disk_read(p->start, s->boot.bytes, 0) ? READ_ERROR : RB_FORMAT_OK;
}

static void hex32(rb_u32 value)
{
    static const char digits[] = "0123456789ABCDEF";
    rb_u16 shift = 32;
    while (shift) { shift -= 4; rb_putc(digits[(value >> shift) & 15U]); }
}

static void span(const char *name, rb_u32 begin, rb_u32 end)
{
    print(name); print(" 0x"); hex32(begin); print(" - 0x"); hex32(end); line("");
}

static const char *boot_status(const observation *s, const rb_partition *p)
{
    rb_volume_probe v;
    rb_u16 i;
    for (i = 0; i < 512 && !s->boot.bytes[i]; ++i) {}
    if (i == 512) { return RB_RS_FP_ZERO; }
    if (rb_probe_volume(&v, p, cached_read, (void *)&s->boot, s->disk.capacity_low, s->disk.capacity_high)) {
        return RB_RS_FP_OTHER;
    }
    return v.fat_bits == 16 ? RB_RS_FP_BPB16 : RB_RS_FP_BPB32;
}

static int same_observation(rb_u16 slot, rb_u16 spc)
{
    return !observe(&second, slot, spc)
        && equal((const rb_u8 *)&first, (const rb_u8 *)&second, sizeof(first));
}

static void target(rb_u16 slot)
{
    print(RB_RS_FP_TARGET); print(" P"); rb_putc('0' + slot); line("");
}

static int display(rb_u16 slot, rb_u16 spc)
{
    static const char *const errors[] = { "", RB_RS_FP_TARGET_BAD, RB_RS_FP_RANGE, RB_RS_FP_CHS,
        RB_RS_FP_EDD, RB_RS_FP_SIZE_BAD, RB_RS_FP_COUNT_BAD, RB_RS_FP_DEVICE,
        RB_RS_FP_TABLE, RB_RS_FP_IO, RB_RS_FP_CHANGED };
    const rb_partition *p = &first.scan.entries[slot - 1];
    const rb_fat_plan *f = &first.plan;
    rb_u16 status = observe(&first, slot, spc);
    if (!status && !same_observation(slot, spc)) { status = CHANGED; }
    target(slot);
    if (status) { line(errors[status]); return 0; }
    print(RB_RS_DISK_ID); print(" 0x"); hex32(first.scan.disk_id); line("");
    print(RB_RS_CAPACITY); print(" 0x"); hex32(first.disk.capacity_high); hex32(first.disk.capacity_low); line("");
    span(RB_RS_FP_VOLUME, p->start, p->start + (p->sectors - 1));
    line(boot_status(&first, p));
    count("FAT", f->bits);
    count(RB_RS_FP_SPC " ", f->spc);
    count(RB_RS_FP_FATSIZE " ", f->sectors_per_fat);
    count(RB_RS_FP_CLUSTERS " ", f->clusters);
    span(RB_RS_FP_RESERVED, p->start, f->fat1 - 1);
    span("FAT 1", f->fat1, f->fat2 - 1);
    span("FAT 2", f->fat2, f->root - 1);
    span(RB_RS_FP_ROOT, f->root, f->bits == 16 ? f->data - 1 : f->root + (f->spc - 1));
    print(RB_RS_FP_DATA); print(" 0x"); hex32(f->data); line("");
    if (f->bits == 32) {
        print(RB_RS_FP_BOOT); print(" 0x"); hex32(p->start); print(" / 0x"); hex32(p->start + 6); line("");
        print(RB_RS_FP_INFO); print(" 0x"); hex32(p->start + 1); print(" / 0x"); hex32(p->start + 7); line("");
    }
    return 1;
}

static int compare_copy(rb_u16 slot, rb_u16 spc, rb_format_comparison *result)
{
    const char *error;
    if (!same_observation(slot, spc)) { line(RB_RS_FP_CHANGED); return 0; }
    error = rb_format_compare(&first, result);
    if (error) {
        line(error);
        if (result->error_lba != RB_FORMAT_NO_LBA) {
            print(RB_RS_FR_ERROR_LBA); print(" 0x"); hex32(result->error_lba); line("");
        }
        return 0;
    }
    if (!same_observation(slot, spc)) { line(RB_RS_FP_CHANGED); return 0; }
    return 1;
}

static void review(rb_u16 slot, rb_u16 spc)
{
    rb_format_comparison shown, repeated;
    rb_u16 key;
    line(RB_RS_FR_READING);
    if (!compare_copy(slot, spc, &shown)) { return; }
    target(slot);
    rb_format_print_pair();
    print(RB_RS_DISK_ID); print(" 0x"); hex32(first.scan.disk_id); line("");
    span(RB_RS_FP_VOLUME, first.boot.lba, first.boot.lba + (first.scan.entries[slot - 1].sectors - 1));
    count("FAT", first.plan.bits);
    count(RB_RS_FP_SPC " ", first.plan.spc);
    span(RB_RS_FR_SPAN, first.boot.lba, shown.last);
    count(RB_RS_FR_SECTORS " ", shown.last - first.boot.lba + 1);
    count(RB_RS_FR_NONZERO " ", shown.nonzero);
    line(RB_RS_FR_LOSS); line(RB_RS_FR_CONFIRM);
    do { key = rb_console_key(); } while (key != 27 && key != 13 && (key < '1' || key > '4'));
    if (key == 27) { line(RB_RS_FR_CANCEL); return; }
    if (key != '0' + slot) { line(RB_RS_FR_WRONG); return; }
    line(RB_RS_FR_READING);
    if (!compare_copy(slot, spc, &repeated)) { return; }
    if (!equal((const rb_u8 *)&shown, (const rb_u8 *)&repeated, sizeof(shown))) {
        line(RB_RS_FP_CHANGED); return;
    }
    line(RB_RS_FR_DONE); line("RB FAT REVIEW PASS");
}

rb_u16 __cdecl rb_fat_plan_run(rb_u16 drive)
{
    rb_u16 key, slot = 0, spc = 0;
    int ready = 0, paired = rb_format_load_pair(drive);
    line(RB_RS_FP_TITLE); line(RB_RS_FP_SCOPE);
    if (paired < 0) { line(RB_RS_FR_PROFILE); }
    if (paired > 0) { line(RB_RS_FR_MODE); }
    for (;;) {
        if (ready) { line(RB_RS_FR_OFFER); }
        line(RB_RS_FP_SELECT);
        do { key = rb_console_key(); } while (key != 27 && (key < '1' || key > '4') && !(ready && key == 'R'));
        if (key == 27) { return 0; }
        ready = 0;
        if (key == 'R') { review(slot, spc); continue; }
        slot = key - '0';
        line(RB_RS_FP_CHOICES); line(RB_RS_FP_AUTO);
        do { key = rb_console_key(); } while (key != 27 && key != 13 && (key < 'A' || key > 'G'));
        if (key == 27) { continue; }
        spc = key == 13 ? 0 : 1U << (key - 'A');
        ready = display(slot, spc) && paired > 0;
    }
}
