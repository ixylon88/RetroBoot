#include "fingerprint.h"
#include "config.h"

void rb_fingerprint_sector(rb_u32 digest[2], rb_u32 address, const rb_u8 *sector)
{
    rb_u32 tuple[3];
    rb_u16 i;
    /* Isolate the trailing CRC from its 508-byte body. Splitting into 256-byte
       halves still cancels a correctly resealed change in the second half.
       Both chains include address and read order. CRC collisions remain
       possible; this is neither authentication nor an atomic snapshot. */
    for (i = 0; i < 2; ++i) {
        tuple[0] = digest[i]; tuple[1] = address;
        tuple[2] = rb_crc32(sector + (i ? 508 : 0), i ? 4 : 508);
        digest[i] = rb_crc32((const rb_u8 *)tuple, sizeof(tuple));
    }
}
