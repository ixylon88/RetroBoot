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
    rb_ata_identity recovery; /* zero capacity for a floppy carrier */
} rb_ata_enrollment;

int rb_ata_identify(rb_ata_identity *result);
int rb_ata_target_can_flush(const rb_ata_enrollment *profile);
int rb_ata_identify_recovery(rb_ata_identity *result, int require_flush);
int rb_ata_recovery_label(const rb_ata_enrollment *profile);
int __cdecl rb_ata_pair_matches(void *profile);
rb_u16 __cdecl rb_ata_read_record(rb_u16 n, rb_u8 *out, rb_u8 *id, void *profile);
rb_u16 __cdecl rb_ata_write_record(rb_u16 n, const rb_u8 *in, const rb_u8 *id, void *profile);
int __cdecl rb_ata_target_matches(void *profile);
int rb_ata_decode_enrollment(rb_ata_enrollment *profile, const rb_u8 *sector);
rb_u16 __cdecl rb_ata_read_mbr(rb_mbr_target *actual, rb_u8 *sector, void *profile);

#endif
