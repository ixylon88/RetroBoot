#include "menu.h"

#define CHECK(condition) do { ++number; if (!(condition)) { return number; } } while (0)

/* Executed by the actual C/16 build in both EDD and CHS boot campaigns. */
rb_u16 __cdecl rb_menu_selftest(void)
{
    rb_menu_state state;
    rb_u16 number = 0;
    rb_menu_init(&state, 3, 5, 0, 183, 100);
    CHECK(state.selected == 0 && state.remaining_ticks == 183);
    CHECK(rb_menu_step(&state, 0x5000, 101) == RB_MENU_NONE && state.selected == 2);
    CHECK(state.remaining_ticks == 0);
    CHECK(rb_menu_step(&state, 0x5000, 102) == RB_MENU_NONE && state.selected == 0);
    CHECK(rb_menu_step(&state, 0x4800, 103) == RB_MENU_NONE && state.selected == 2);
    CHECK(rb_menu_step(&state, 0x1C0D, 104) == 2);
    rb_menu_init(&state, 3, 5, 1, 183, 100);
    CHECK(state.selected == 0 && state.remaining_ticks == 0);
    rb_menu_init(&state, 0, 0, 0, 183, 100);
    CHECK(state.selected == RB_MENU_NONE && rb_menu_step(&state, 0x1C0D, 101) == RB_MENU_NONE);
    rb_menu_init(&state, 9, 0xFFFF, 0, 183, 100);
    CHECK(state.selected == RB_MENU_NONE && state.remaining_ticks == 0);
    rb_menu_init(&state, 3, 0, 0, 183, 100);
    CHECK(state.selected == RB_MENU_NONE);
    rb_menu_init(&state, 3, 7, 1, 183, 100);
    CHECK(rb_menu_step(&state, RB_KEY_NONE, 200) == RB_MENU_NONE && state.remaining_ticks == 83);
    CHECK(rb_menu_step(&state, RB_KEY_NONE, 282) == RB_MENU_NONE && state.remaining_ticks == 1);
    CHECK(rb_menu_step(&state, RB_KEY_NONE, 283) == 1 && state.remaining_ticks == 0);
    CHECK(rb_menu_step(&state, RB_KEY_NONE, 284) == RB_MENU_NONE);
    rb_menu_init(&state, 3, 7, 2, 10, RB_TICKS_PER_DAY - 5);
    CHECK(rb_menu_step(&state, RB_KEY_NONE, 4) == RB_MENU_NONE && state.remaining_ticks == 1);
    CHECK(rb_menu_step(&state, RB_KEY_NONE, 5) == 2);
    rb_menu_init(&state, 3, 7, 0, 183, 100);
    CHECK(rb_menu_step(&state, RB_KEY_NONE, 100) == RB_MENU_NONE && state.remaining_ticks == 183);
    CHECK(rb_menu_step(&state, RB_KEY_NONE, 99) == RB_MENU_NONE && state.remaining_ticks == 0);
    rb_menu_init(&state, 3, 7, 0, 183, 100);
    CHECK(rb_menu_step(&state, RB_KEY_NONE, 1000) == RB_MENU_NONE && state.remaining_ticks == 0);
    rb_menu_init(&state, 3, 7, 0, 183, RB_TICKS_PER_DAY);
    CHECK(state.remaining_ticks == 0);
    rb_menu_init(&state, 3, 7, 0, 183, 100);
    CHECK(rb_menu_step(&state, RB_KEY_NONE, RB_TICKS_PER_DAY) == RB_MENU_NONE && state.remaining_ticks == 0);
    rb_menu_init(&state, 3, 7, 0, 183, 100);
    CHECK(rb_menu_step(&state, 0x011B, 283) == RB_MENU_NONE && state.remaining_ticks == 0);
    rb_menu_init(&state, 3, 7, 0, 183, 100);
    CHECK(rb_menu_step(&state, 0x1E61, 283) == RB_MENU_NONE && state.remaining_ticks == 0);
    rb_menu_init(&state, 3, 7, 0, 183, 100);
    CHECK(rb_menu_step(&state, 0, 283) == RB_MENU_NONE && state.remaining_ticks == 0);
    rb_menu_init(&state, 3, 7, 0, 0, 100);
    CHECK(rb_menu_step(&state, RB_KEY_NONE, 10000) == RB_MENU_NONE);
    rb_menu_init(&state, 3, 7, 0, 1094, 100);
    CHECK(state.remaining_ticks == 0);
    return 0;
}
