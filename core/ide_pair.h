#ifndef RB_IDE_PAIR_H
#define RB_IDE_PAIR_H
#include "rescue.h"

/* A blank profile permits a read-only preview. A writer requires a matched pair. */
int rb_ide_load_pair(rb_u16 drive);
void rb_ide_print_pair(void);
const char *rb_ide_check_pair(rb_u32 capacity_low, rb_u32 capacity_high);
rb_u32 rb_ide_pair_crc(void);
int rb_ide_can_flush(void);
rb_u16 __cdecl rb_ata_copy_read(rb_u16 channel, rb_u32 lba, rb_u8 *out);
#endif
