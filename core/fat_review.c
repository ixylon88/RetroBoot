/* Verify the original bytes of the proposed metadata range on a separate IDE master. */
#include "fat_review.h"
#include "volume.h"
#include "config.h"
#include "fingerprint.h"
#include "mbr_ata.h"
#include "mbr_console.h"
#include "mbr_compare.h"
#include "rescue_file.h"
#include "rescue_text.h"


static rb_ata_enrollment pair;
static rb_u16 floppy;
static rb_u8 enrolled[512], source[512], copy[512], bios_table[512];

static int occupied(const rb_u8 *sector)
{
    rb_u16 i;
    for (i = 0; i < 512; ++i) {
        if (sector[i]) { return 1; }
    }
    return 0;
}

int rb_format_load_pair(rb_u16 drive)
{
    floppy = drive;
    if (rb_floppy_read(2879, enrolled, &floppy)) { return -1; }
    if (!occupied(enrolled)) { return 0; }
    if (!equal(enrolled, (const rb_u8 *)"RBTARG03", 8)
            || !rb_ata_decode_enrollment(&pair, enrolled)
            || pair.device.sectors_low != pair.recovery.sectors_low
            || pair.device.sectors_high != pair.recovery.sectors_high) { return -1; }
    return 1;
}

static void serial(const char *label, const rb_ata_identity *device)
{
    rb_u16 i, n = sizeof(device->serial);
    while (n && device->serial[n - 1] == ' ') { --n; }
    print(label); rb_putc(' ');
    for (i = 0; i < n; ++i) { rb_putc(device->serial[i]); }
    line("");
}

void rb_format_print_pair(void)
{
    serial(RB_RS_FR_SOURCE, &pair.device);
    serial(RB_RS_FR_COPY, &pair.recovery);
}

static const char *check_devices(const rb_rescue_device *disk)
{
    rb_ata_identity live;
    if (rb_floppy_read(2879, copy, &floppy) || !equal(enrolled, copy, 512)) { return RB_RS_FR_PROFILE; }
    if (disk->capacity_low != pair.device.sectors_low || disk->capacity_high != pair.device.sectors_high
            || !rb_ata_identify(&live) || !equal((const rb_u8 *)&live, (const rb_u8 *)&pair.device, sizeof(live))) {
        return RB_RS_FR_SOURCE_BAD;
    }
    if (!rb_ata_identify_recovery(&live, 0)
            || !equal((const rb_u8 *)&live, (const rb_u8 *)&pair.recovery, sizeof(live))) { return RB_RS_FR_COPY_BAD; }
    return 0;
}

static const char *compare_sector(rb_u32 lba, const rb_u8 *bios_view, rb_format_comparison *result)
{
    result->error_lba = lba;
    if (rb_ata_copy_read(0, lba, source) || rb_ata_copy_read(1, lba, copy)) { return RB_RS_FR_IO; }
    if (bios_view && !equal(source, bios_view, 512)) { return RB_RS_FP_CHANGED; }
    if (!equal(source, copy, 512)) { return RB_RS_FR_DIFFERENT; }
    return 0;
}

rb_u32 rb_format_pair_crc(void)
{
    return rb_crc32(enrolled, 508);
}

int rb_format_can_flush(void)
{
    return rb_ata_target_can_flush(&pair);
}

const char *rb_format_check_tables(const observation *v, rb_format_comparison *r)
{
    const char *error;
    rb_u16 i;
    rb_u32 lba;
    error = check_devices(&v->disk);
    if (error) { return error; }
    error = compare_sector(0, v->mbr.bytes, r);
    if (error) { return error; }
    for (i = 0; i < v->scan.ebr_count; ++i) {
        lba = v->scan.ebr_lba[i];
        r->error_lba = lba;
        if (lba > 0x0fffffffUL) { return RB_RS_FR_LBA28; }
        if (rb_disk_read(lba, bios_table, 0)) { return RB_RS_FR_IO; }
        error = compare_sector(lba, bios_table, r);
        if (error) { return error; }
        rb_fingerprint_sector(r->fingerprint, lba, source);
    }
    return 0;
}

rb_u32 rb_fat_metadata_last(const rb_fat_plan *plan)
{
    return plan->bits == 16 ? plan->data - 1 : plan->root + (plan->spc - 1);
}

const char *rb_format_compare(const observation *v, rb_format_comparison *r)
{
    const rb_fat_plan *f = &v->plan;
    const char *error;
    rb_u32 lba;
    clear((rb_u8 *)r, sizeof(*r));
    r->error_lba = RB_FORMAT_NO_LBA;
    r->last = rb_fat_metadata_last(f);
    if (r->last < v->boot.lba || r->last > 0x0fffffffUL) { return RB_RS_FR_LBA28; }
    error = rb_format_check_tables(v, r);
    if (error) { return error; }
    for (lba = v->boot.lba; lba <= r->last; ++lba) {
        error = compare_sector(lba, lba == v->boot.lba ? v->boot.bytes : 0, r);
        if (error) { return error; }
        /* In a fixed range every omitted address denotes an all-zero sector. */
        if (occupied(source)) {
            ++r->nonzero;
            rb_fingerprint_sector(r->fingerprint, lba, source);
        }
    }
    r->error_lba = RB_FORMAT_NO_LBA;
    return check_devices(&v->disk);
}

rb_u16 __cdecl rb_fat_cached_read(rb_u32 lba, rb_u8 *sector, void *opaque)
{
    const sector_copy *saved = opaque;
    rb_u16 i;
    if (lba != saved->lba) { return rb_disk_read(lba, sector, 0); }
    for (i = 0; i < 512; ++i) { sector[i] = saved->bytes[i]; }
    return 0;
}

rb_u16 rb_fat_observe(observation *s, rb_u16 slot, rb_u16 spc)
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
    if (rb_scan_partitions(&s->scan, rb_fat_cached_read, &s->mbr, s->disk.capacity_low, s->disk.capacity_high, id)) {
        return s->scan.status == RB_SCAN_IO ? READ_ERROR : BAD_TABLE;
    }
    p = &s->scan.entries[slot - 1];
    status = rb_plan_primary_fat(&s->plan, p, mbr + 446 + (slot - 1) * 16,
                                 &s->disk, s->geometry, spc);
    if (status) { return status; }
    s->boot.lba = p->start;
    return rb_disk_read(p->start, s->boot.bytes, 0) ? READ_ERROR : RB_FORMAT_OK;
}

void rb_fat_hex32(rb_u32 value)
{
    static const char digits[] = "0123456789ABCDEF";
    rb_u16 shift = 32;
    while (shift) { shift -= 4; rb_putc(digits[(value >> shift) & 15U]); }
}

void rb_fat_span(const char *name, rb_u32 begin, rb_u32 end)
{
    print(name); print(" 0x"); rb_fat_hex32(begin); print(" - 0x"); rb_fat_hex32(end); line("");
}
