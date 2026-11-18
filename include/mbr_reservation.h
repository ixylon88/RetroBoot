#ifndef RB_MBR_RESERVATION_H
#define RB_MBR_RESERVATION_H

#include "mbr_restart.h"

enum { RB_RESERVE_START, RB_RESERVE_DATA, RB_RESERVE_RETURN };
enum { RB_RESERVE_FULL = RB_REOPEN_CHANGED + 1 };

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
} rb_mbr_reservation_io;

/* Only the returned number is released. On every failure it is zero.
   A successfully advanced witness can burn a number even if the call fails. */
rb_u16 rb_mbr_reserve_number(rb_u32 *number, const rb_mbr_binding *enrollment,
                             const rb_u8 *witness_id, const rb_mbr_reservation_io *io);

#endif
