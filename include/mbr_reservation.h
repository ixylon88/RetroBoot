#ifndef RB_MBR_RESERVATION_H
#define RB_MBR_RESERVATION_H

#include "mbr_exchange.h"

enum { RB_RESERVE_START = RB_MBR_START_WITNESS, RB_RESERVE_DATA = RB_MBR_SELECT_CARRIER,
       RB_RESERVE_RETURN = RB_MBR_RETURN_WITNESS };
enum { RB_RESERVE_FULL = RB_REOPEN_CHANGED + 1 };

typedef rb_mbr_exchange rb_mbr_reservation_io;

/* Only the returned number is released. On every failure it is zero.
   A successfully advanced witness can burn a number even if the call fails. */
rb_u16 rb_mbr_reserve_number(rb_u32 *number, const rb_mbr_binding *enrollment,
                             const rb_u8 *witness_id, const rb_mbr_reservation_io *io);

#endif
