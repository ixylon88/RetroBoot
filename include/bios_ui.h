#ifndef RB_BIOS_UI_H
#define RB_BIOS_UI_H

#include "abi.h"

typedef struct {
    rb_u32 heads;
    rb_u32 sectors_per_track;
    rb_u8 mbr[512];
} rb_loader_snapshot;

typedef char rb_check_snapshot_size[(sizeof(rb_loader_snapshot) == 520) ? 1 : -1];

void __cdecl rb_video_init(void);
void __cdecl rb_video_fill(rb_u16 cell, rb_u16 count, rb_u16 character_attribute);
void __cdecl rb_video_text(rb_u16 cell, const char *text, rb_u16 attribute);
/* INT 13h/08h geometry of BIOS disk 0x80, or three zeros on failure. */
void __cdecl rb_dos_geometry(rb_u16 *geometry);
void __cdecl rb_loader_copy(rb_loader_snapshot *snapshot);
rb_u16 __cdecl rb_key_poll(void); /* BIOS scan:ASCII, FFFFh means no key */
rb_u32 __cdecl rb_ticks(void);
void __cdecl rb_idle(void);
void __cdecl rb_debug_putc(rb_u16 character);

#endif
