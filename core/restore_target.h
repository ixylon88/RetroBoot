/* Read-only checks shared by independently booted, enrolled repairs. */
#ifndef RB_RESTORE_TARGET_H
#define RB_RESTORE_TARGET_H

#include "backup_store.h"
#include "mbr_compare.h"
#include "mbr_console.h"
#include "rescue_text.h"

static int same_source(void)
{
    rb_mbr_target id;
    return !rb_store.source.identify(&id, (void *)0);
}

static int read_live(rb_u32 lba, rb_u8 *out)
{
    return rb_store.source.read(lba, out, (void *)0) == 0;
}

static int mbr_only(const rb_backup *saved, rb_u8 *scratch)
{
    return !saved->capacity_high && saved->capacity_low >= 3 && saved->capacity_low <= 0x10000000UL
        && read_live(1, scratch) && !equal(scratch, (const rb_u8 *)"EFI PART", 8)
        && read_live(saved->capacity_low - 1, scratch) && !equal(scratch, (const rb_u8 *)"EFI PART", 8);
}

static void show_source(const rb_ata_enrollment *profile)
{
    rb_u16 i, n = sizeof(profile->device.serial);
    while (n && profile->device.serial[n - 1] == ' ') { --n; }
    print(RB_RS_D_SERIAL); rb_putc(' ');
    for (i = 0; i < n; ++i) { rb_putc(profile->device.serial[i]); }
    line("");
    count(RB_RS_STORE_REV, rb_store.witness.commit.approved);
}

#endif
