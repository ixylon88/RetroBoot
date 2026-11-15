#include "fat_boot.h"

static rb_u32 dword(const rb_u8 *p)
{
    return (rb_u32)p[0] | ((rb_u32)p[1] << 8)
        | ((rb_u32)p[2] << 16) | ((rb_u32)p[3] << 24);
}

rb_u16 rb_fat32_fsinfo(const rb_u8 *sector, rb_u32 clusters)
{
    rb_u16 i;
    rb_u32 value;
    if (dword(sector) != 0x41615252UL || dword(sector + 484) != 0x61417272UL
            || dword(sector + 508) != 0xAA550000UL) { return 1; }
    for (i = 4; i < 508; ++i) {
        if ((i < 484 || i >= 496) && sector[i]) { return 2; }
    }
    value = dword(sector + 488);
    if (value != 0xFFFFFFFFUL && value > clusters) { return 3; }
    value = dword(sector + 492);
    if (value != 0xFFFFFFFFUL && (value < 2 || value > clusters + 1)) { return 4; }
    return 0;
}
