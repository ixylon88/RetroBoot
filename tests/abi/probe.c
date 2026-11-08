#include "abi.h"

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

rb_u16 __cdecl rb_probe(rb_u16 boot_drive)
{
    rb_u16 local = 0xA55A;
    rb_u16 index;
    volatile rb_u32 value = 0x1234ABCDUL;
    const volatile rb_u16 __far *far_data = &rb_initialized_word;

    if (boot_drive != 0 || rb_check_context(&local) != 0) {
        print("C context FAIL\r\n");
        return 1;
    }
    if (rb_bss_word != 0 || rb_bss_long != 0) {
        print("C BSS FAIL\r\n");
        return 2;
    }
    for (index = 0; index < sizeof(rb_bss_array); ++index) {
        if (rb_bss_array[index] != 0) {
            print("C BSS array FAIL\r\n");
            return 3;
        }
    }
    if (rb_initialized_word != 0x4B52 || rb_initialized_long != 0x89ABCDEFUL
            || rb_far_read(far_data) != 0x4B52) {
        print("C data FAIL\r\n");
        return 4;
    }
    if (rb_asm_mix(value, 0x10) != 0x1234ABDDUL
            || (value >> 8) != 0x001234ABUL
            || value - 0x12340000UL != 0xABCDUL) {
        print("C integer ABI FAIL\r\n");
        return 5;
    }
    rb_bss_word = 0xBEAD;           /* prove that the data segment is writable */
    if (rb_bss_word != 0xBEAD) {
        return 6;
    }
    print("C entry, data, BSS, pointers and integer calls OK\r\n");
    return 0;
}
