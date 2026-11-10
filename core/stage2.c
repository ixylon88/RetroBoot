#include "stage2.h"

rb_boot_context rb_boot;
volatile rb_u16 rb_initialized_word = 0x4B52;
volatile rb_u32 rb_initialized_long = 0x89ABCDEFUL;
volatile rb_u16 rb_bss_word;
volatile rb_u32 rb_bss_long;
volatile rb_u8 rb_bss_array[17];

static void print(const char *message)
{
    while (*message != 0) {
        rb_putc((rb_u8)*message++);
    }
}

rb_u32 __cdecl rb_c_mix(rb_u32 value, rb_u16 increment)
{
    return value + increment;
}

/* First HDD C entry: establish the runtime before adding menu/disk services. */
rb_u16 __cdecl rb_main(const rb_boot_context *boot)
{
    rb_u16 local = 0xA55A;
    rb_u16 index;
    volatile rb_u32 value = 0x1234ABCDUL;
    const volatile rb_u16 __far *far_data = &rb_initialized_word;

    if (boot != &rb_boot || boot->drive != 0x80 || boot->io_mode > 1
            || (boot->reachable_sectors_low == 0 && boot->reachable_sectors_high == 0)
            || rb_check_context(&local) != 0) {
        print("C context ERROR\r\n");
        return 1;
    }
    if (rb_bss_word != 0 || rb_bss_long != 0) {
        print("C BSS ERROR\r\n");
        return 2;
    }
    for (index = 0; index < sizeof(rb_bss_array); ++index) {
        if (rb_bss_array[index] != 0) {
            print("C BSS array ERROR\r\n");
            return 3;
        }
    }
    if (rb_initialized_word != 0x4B52 || rb_initialized_long != 0x89ABCDEFUL
            || rb_far_read(far_data) != 0x4B52) {
        print("C data ERROR\r\n");
        return 4;
    }
    if (rb_asm_mix(value, 0x10) != 0x1234ABDDUL
            || (value >> 8) != 0x001234ABUL
            || value - 0x12340000UL != 0xABCDUL) {
        print("C integer ABI ERROR\r\n");
        return 5;
    }
    rb_bss_word = 0xBEAD;
    if (rb_bss_word != 0xBEAD) {
        return 6;
    }
    print("C entry, data, BSS, pointers and integer calls OK\r\n");
    print(boot->io_mode == 1 ? "BIOS disk path: EDD\r\n" : "BIOS disk path: CHS\r\n");
    return 0;
}
