#ifndef RB_MBR_EXCHANGE_H
#define RB_MBR_EXCHANGE_H

#include "mbr_restart.h"

enum { RB_MBR_START_WITNESS, RB_MBR_SELECT_CARRIER, RB_MBR_RETURN_WITNESS };

/* One exclusive writer owns the two enrolled media for the whole operation.
   select returns zero when the requested medium is available. read identifies
   the actual endpoint. write checks the expected endpoint before modifying it
   and reports 512 only after the sector is durable. Inputs are disjoint. */
typedef struct {
    rb_u16 (__cdecl *select)(rb_u16 phase, void *opaque);
    rb_mbr_restart_reader read;
    rb_u16 (__cdecl *write)(rb_u16 sector, const rb_u8 *bytes,
                            const rb_u8 *expected_endpoint, void *opaque);
    void *opaque;
} rb_mbr_exchange;

#endif
