#ifndef RB_FAT_BOOT_H
#define RB_FAT_BOOT_H

#include "abi.h"

/* Shared structural FSInfo check for saved and live FAT32 boot areas.
   Returns 0, or 1=signatures, 2=reserved bytes, 3=free count, 4=next hint. */
rb_u16 rb_fat32_fsinfo(const rb_u8 *sector, rb_u32 clusters);

#endif
