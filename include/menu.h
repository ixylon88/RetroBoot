#ifndef RB_MENU_H
#define RB_MENU_H

#include "abi.h"

#define RB_KEY_NONE 0xFFFFU
#define RB_MENU_NONE 0xFFFFU
#define RB_MENU_MAX 8U
#define RB_TICKS_PER_DAY 0x1800B0UL

/* No I/O or boot action: this model only returns a selected entry index. */
typedef struct {
    rb_u16 count;
    rb_u16 enabled;
    rb_u16 selected;
    rb_u16 remaining_ticks;
    rb_u32 previous_tick;
} rb_menu_state;

void rb_menu_init(rb_menu_state *state, rb_u16 count, rb_u16 enabled,
                  rb_u16 default_index, rb_u16 timeout_ticks, rb_u32 now);
rb_u16 rb_menu_step(rb_menu_state *state, rb_u16 key, rb_u32 now);
void __cdecl rb_menu_run(void);
rb_u16 __cdecl rb_menu_selftest(void);

#endif
