#ifndef RB_MBR_FLOPPY_H
#define RB_MBR_FLOPPY_H

#include "abi.h"

typedef struct {
    rb_u16 drive, base, sectors;
    const rb_u8 *id;
} capture_medium;

rb_u16 __cdecl rb_fixture_floppy_write(rb_u32 lba, const rb_u8 *in, void *boot_drive);

int rb_mbr_label_matches(const rb_u8 *bytes, const rb_u8 *id);
int rb_mbr_floppy_matches(capture_medium *medium);
rb_u16 __cdecl rb_mbr_floppy_read(rb_u16 n, rb_u8 *out, rb_u8 *id, void *opaque);
rb_u16 __cdecl rb_mbr_floppy_save_original(rb_u16 n, const rb_u8 *in, const rb_u8 *id, void *opaque);

#endif
