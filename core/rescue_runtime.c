#include "rescue.h"
#include "bios_ui.h"

volatile rb_u16 rb_rescue_initialized = 0x5242;
volatile rb_u8 rb_rescue_bss[32];

rb_u16 __cdecl rb_rescue_runtime(void)
{
    rb_u16 i, local = 0xA55A;
    if (rb_rescue_initialized != 0x5242 || rb_check_context(&local)) { return 1; }
    for (i = 0; i < sizeof(rb_rescue_bss); ++i) { if (rb_rescue_bss[i]) { return 1; } }
    return 0;
}
