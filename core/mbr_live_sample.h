#ifndef RB_MBR_LIVE_SAMPLE_H
#define RB_MBR_LIVE_SAMPLE_H

#include "mbr_restart.h"
#include "mbr_current.h"

/* Translate the live-reader contract into the publication and reopen status domain. */
static __inline rb_u16 sample_mbr(const rb_mbr_target *target, rb_mbr_current_reader read,
                                  void *disk, rb_u8 *bytes)
{
    rb_u16 rc = read_bound_mbr(target, read, disk, bytes);
    if (rc == RB_MBR_BINDING) { return RB_REOPEN_BINDING; }
    return rc == RB_MBR_OK ? RB_REOPEN_OK : RB_REOPEN_IO;
}

static rb_u16 recheck_mbr(const rb_mbr_target *target, const rb_u8 *expected,
                                   rb_mbr_current_reader read, void *disk)
{
    rb_u8 bytes[512];
    rb_u16 rc = sample_mbr(target, read, disk, bytes);
    if (rc) { return rc; }
    return equal(bytes, expected, 512) ? RB_REOPEN_OK : RB_REOPEN_CHANGED;
}

#endif
