#ifndef RB_MBR_ATA_H
#define RB_MBR_ATA_H

#include "mbr_provenance.h"

/* Printed ASCII, left justified and space padded in ATA word order after decoding. */
typedef struct {
    rb_u8 serial[20], model[40];
    rb_u32 sectors_low, sectors_high;
} rb_ata_identity;

typedef struct {
    rb_mbr_binding binding;
    rb_ata_identity device;
    rb_u8 witness_id[16]; /* zero on capture-only RBTARG01 media */
} rb_ata_enrollment;

int rb_ata_identify(rb_ata_identity *result);
int __cdecl rb_ata_target_matches(void *profile);
int rb_ata_decode_enrollment(rb_ata_enrollment *profile, const rb_u8 *sector);
rb_u16 __cdecl rb_ata_read_mbr(rb_mbr_target *actual, rb_u8 *sector, void *profile);

#endif
