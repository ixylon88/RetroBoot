#ifndef RB_MBR_CONSOLE_H
#define RB_MBR_CONSOLE_H
#include "bios_ui.h"

static __inline rb_u16 rb_console_key(void)
{
    rb_u16 key;
    do {
        key = rb_key_poll();
        if (key == 0xffff) { rb_idle(); }
    } while (key == 0xffff);
    key &= 255;
    return key >= 'a' && key <= 'z' ? key - 'a' + 'A' : key;
}

static __inline void print(const char *s)
{
    while (*s) { rb_putc(*s++); }
}

static __inline void line(const char *s)
{
    print(s); rb_putc(13); rb_putc(10);
}

static __inline void count(const char *s, rb_u32 value)
{
    char digits[11];
    rb_u16 i = 10;
    digits[i] = 0;
    do { digits[--i] = (char)('0' + value % 10); value /= 10; } while (value);
    print(s); line(digits + i);
}

#endif
