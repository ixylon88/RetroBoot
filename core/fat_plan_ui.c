/* Read-only installer preview on an independently booted rescue floppy. */
#include "fat_plan.h"
#include "volume.h"
#include "mbr_console.h"
#include "mbr_compare.h"
#include "rescue_text.h"

enum { NO_DEVICE = RB_FORMAT_CLUSTER_COUNT + 1, BAD_TABLE, READ_ERROR, CHANGED };
typedef struct {
    rb_u32 lba;
    rb_u8 bytes[512];
} sector_copy;

typedef struct {
    rb_rescue_device disk;
    rb_u16 geometry[3];
    rb_partition_scan scan;
    sector_copy mbr, boot;
    rb_fat_plan plan;
} observation;

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

static void display(rb_u16 slot, rb_u16 spc)
{
    static const char *const errors[] = { "", RB_RS_FP_TARGET_BAD, RB_RS_FP_RANGE, RB_RS_FP_CHS,
        RB_RS_FP_EDD, RB_RS_FP_SIZE_BAD, RB_RS_FP_COUNT_BAD, RB_RS_FP_DEVICE,
        RB_RS_FP_TABLE, RB_RS_FP_IO, RB_RS_FP_CHANGED };
    const rb_partition *p = &first.scan.entries[slot - 1];
    const rb_fat_plan *f = &first.plan;
    rb_u16 status = observe(&first, slot, spc);
    if (!status && (observe(&second, slot, spc) || !equal((const rb_u8 *)&first, (const rb_u8 *)&second, sizeof(first)))) {
        status = CHANGED;
    }
    print(RB_RS_FP_TARGET); print(" P"); rb_putc('0' + slot); line("");
    if (status) { line(errors[status]); return; }
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
}

rb_u16 __cdecl rb_fat_plan_run(rb_u16 drive)
{
    rb_u16 key, slot, spc;
    (void)drive;
    line(RB_RS_FP_TITLE); line(RB_RS_FP_SCOPE);
    for (;;) {
        line(RB_RS_FP_SELECT);
        do { key = rb_console_key(); } while (key != 27 && (key < '1' || key > '4'));
        if (key == 27) { return 0; }
        slot = key - '0';
        line(RB_RS_FP_CHOICES); line(RB_RS_FP_AUTO);
        do { key = rb_console_key(); } while (key != 27 && key != 13 && (key < 'A' || key > 'G'));
        if (key == 27) { continue; }
        spc = key == 13 ? 0 : 1U << (key - 'A');
        display(slot, spc);
    }
}
