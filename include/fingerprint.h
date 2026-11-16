#ifndef RB_FINGERPRINT_H
#define RB_FINGERPRINT_H

#include "abi.h"

/* Append one successful 512-byte read; start both chains at zero.
   The address is physical or file-relative according to the caller. */
void rb_fingerprint_sector(rb_u32 digest[2], rb_u32 address, const rb_u8 *sector);

#endif
