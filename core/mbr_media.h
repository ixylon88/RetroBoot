/* Exact sector transfers on independently identified MBR media. */
#ifndef RB_MBR_MEDIA_H
#define RB_MBR_MEDIA_H

#include "mbr_exchange.h"
#include "mbr_compare.h"

static __inline rb_u16 acquire(const rb_mbr_restart_source *s, const rb_u8 *expected_id,
                      rb_u16 sector, rb_u8 *out)
{
    rb_u8 id[16] = {0};
    if (s->read(sector, out, id, s->opaque) != 512) { return RB_REOPEN_IO; }
    return equal(id, expected_id, sizeof(id)) ? RB_REOPEN_OK : RB_REOPEN_BINDING;
}

static __inline rb_u16 write_checked(const rb_mbr_exchange *io, rb_u16 sector,
                            const rb_u8 *bytes, const rb_u8 *endpoint)
{
    rb_u8 readback[512], actual[16] = {0};
    if (io->write(sector, bytes, endpoint, io->opaque) != 512
        || io->read(sector, readback, actual, io->opaque) != 512) { return RB_REOPEN_IO; }
    if (!equal(actual, endpoint, 16)) { return RB_REOPEN_BINDING; }
    return equal(bytes, readback, 512) ? RB_REOPEN_OK : RB_REOPEN_CHANGED;
}

#endif
