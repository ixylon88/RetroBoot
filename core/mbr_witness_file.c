#include "rescue_file.h"
#include "mbr_compare.h"

int rb_rescue_witness_extent(rb_rescue_file *file, rb_sector_reader read, void *opaque,
                             rb_u16 lba, int writable)
{
    /* prepare_mbr_target puts the two file entries in slots 2 and 3. */
    static const rb_u8 profile_extent[6] = {0x20, 0x0B, 0, 2, 0, 0};
    rb_u8 directory[512];
    rb_u16 i;
    if (read(19, directory, opaque)
        || !equal(directory + 64, (const rb_u8 *)"RBTARGETBIN\x01", 12)
        || !equal(directory + 90, profile_extent, 6)
        || !equal(directory + 96, (const rb_u8 *)"RBWITNESBIN", 11)
        || (writable && (directory[107] & 1))) { return 0; }
    rb_rescue_file_open_named(file, read, opaque, "RBWITNESBIN");
    if (!file->ready || file->sectors != 5) { return 0; }
    for (i = 0; i < 5; ++i) {
        if (rb_rescue_file_lba(file, i) != lba + i) { return 0; }
    }
    return 1;
}
