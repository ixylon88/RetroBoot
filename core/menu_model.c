#include "menu.h"

static rb_u16 enabled(const rb_menu_state *state, rb_u16 index)
{
    return index < state->count && (state->enabled & (1U << index)) != 0;
}

void rb_menu_init(rb_menu_state *state, rb_u16 count, rb_u16 mask,
                  rb_u16 default_index, rb_u16 timeout_ticks, rb_u32 now)
{
    rb_u16 index;
    state->count = count <= RB_MENU_MAX ? count : 0;
    state->enabled = mask;
    state->selected = RB_MENU_NONE;
    state->remaining_ticks = 0;
    state->previous_tick = now;
    if (enabled(state, default_index)) {
        state->selected = default_index;
        if (now < RB_TICKS_PER_DAY && timeout_ticks <= 1093U) {
            state->remaining_ticks = timeout_ticks;
        }
    } else {
        /* A fallback selection never silently becomes an automatic default. */
        for (index = 0; index < state->count; ++index) {
            if (enabled(state, index)) {
                state->selected = index;
                break;
            }
        }
    }
}

rb_u16 rb_menu_step(rb_menu_state *state, rb_u16 key, rb_u32 now)
{
    rb_u16 index, scan;
    rb_u32 elapsed;
    if (key != RB_KEY_NONE) {
        state->remaining_ticks = 0; /* Every key cancels, including unknown keys. */
        if (!enabled(state, state->selected)) {
            return RB_MENU_NONE;
        }
        scan = key >> 8;
        if (scan == 0x48U || scan == 0x50U) {
            for (index = 0; index < state->count; ++index) {
                if (scan == 0x48U) {
                    state->selected = state->selected == 0 ? state->count - 1 : state->selected - 1;
                } else {
                    state->selected = state->selected + 1 == state->count ? 0 : state->selected + 1;
                }
                if (enabled(state, state->selected)) {
                    break;
                }
            }
        } else if ((key & 0xFFU) == 13U) {
            return state->selected;
        }
        return RB_MENU_NONE;
    }
    if (state->remaining_ticks == 0) {
        return RB_MENU_NONE;
    }
    if (now >= RB_TICKS_PER_DAY || state->previous_tick >= RB_TICKS_PER_DAY) {
        state->remaining_ticks = 0;
        return RB_MENU_NONE;
    }
    elapsed = now >= state->previous_tick ? now - state->previous_tick
              : RB_TICKS_PER_DAY - state->previous_tick + now;
    state->previous_tick = now;
    /* A backwards clock or long unexplained gap must not trigger a boot. */
    if (elapsed > 182UL || !enabled(state, state->selected)) {
        state->remaining_ticks = 0;
        return RB_MENU_NONE;
    }
    if (elapsed >= state->remaining_ticks) {
        state->remaining_ticks = 0;
        return state->selected;
    }
    state->remaining_ticks -= (rb_u16)elapsed;
    return RB_MENU_NONE;
}
