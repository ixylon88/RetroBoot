#ifndef RB_MBR_CURRENT_H
#define RB_MBR_CURRENT_H

#include "mbr_provenance.h"
#include "mbr_bytes.h"

static rb_u16 read_bound_mbr(const rb_mbr_target *expected, rb_mbr_current_reader read,
                             void *disk, rb_u8 *sector)
{
    rb_mbr_target actual;
    clear((rb_u8 *)&actual, sizeof(actual));
    if (read(&actual, sector, disk) != 512) { return RB_MBR_LIVE_IO; }
    return same_target(&actual, expected) ? RB_MBR_OK : RB_MBR_BINDING;
}

#endif
