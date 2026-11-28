/* Verify the original bytes of the proposed metadata range on a separate IDE master. */
#include "fat_review.h"
#include "fingerprint.h"
#include "mbr_ata.h"
#include "mbr_console.h"
#include "mbr_compare.h"
#include "rescue_file.h"
#include "rescue_text.h"

rb_u16 __cdecl rb_ata_copy_read(rb_u16 channel, rb_u32 lba, rb_u8 *out);

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

const char *rb_format_compare(const observation *v, rb_format_comparison *r)
{
    const rb_fat_plan *f = &v->plan;
    const char *error;
    rb_u16 i;
    rb_u32 lba;
    clear((rb_u8 *)r, sizeof(*r));
    r->error_lba = RB_FORMAT_NO_LBA;
    r->last = f->bits == 16 ? f->data - 1 : f->root + (f->spc - 1);
    if (r->last < v->boot.lba || r->last > 0x0fffffffUL) { return RB_RS_FR_LBA28; }
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
