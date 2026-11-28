/* Binding of the primary and secondary IDE masters to the external boot profile. */
#include "ide_pair.h"
#include "config.h"
#include "mbr_ata.h"
#include "mbr_compare.h"
#include "mbr_console.h"
#include "rescue_file.h"
#include "rescue_text.h"

static rb_ata_enrollment pair;
static rb_u16 floppy;
static rb_u8 enrolled[512], copy[512];

int rb_ide_load_pair(rb_u16 drive)
{
    static const rb_u8 zero[512] = {0};
    floppy = drive;
    if (rb_floppy_read(2879, enrolled, &floppy)) { return -1; }
    if (equal(enrolled, zero, 512)) { return 0; }
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

void rb_ide_print_pair(void)
{
    serial(RB_RS_FR_SOURCE, &pair.device);
    serial(RB_RS_FR_COPY, &pair.recovery);
}

const char *rb_ide_check_pair(rb_u32 capacity_low, rb_u32 capacity_high)
{
    rb_ata_identity live;
    if (rb_floppy_read(2879, copy, &floppy) || !equal(enrolled, copy, 512)) { return RB_RS_FR_PROFILE; }
    if (capacity_low != pair.device.sectors_low || capacity_high != pair.device.sectors_high
            || !rb_ata_identify(&live) || !equal((const rb_u8 *)&live, (const rb_u8 *)&pair.device, sizeof(live))) {
        return RB_RS_FR_SOURCE_BAD;
    }
    if (!rb_ata_identify_recovery(&live, 0)
            || !equal((const rb_u8 *)&live, (const rb_u8 *)&pair.recovery, sizeof(live))) { return RB_RS_FR_COPY_BAD; }
    return 0;
}

rb_u32 rb_ide_pair_crc(void)
{
    return rb_crc32(enrolled, 508);
}

int rb_ide_can_flush(void)
{
    return rb_ata_target_can_flush(&pair);
}
