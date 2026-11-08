#ifndef RB_ABI_H
#define RB_ABI_H

/* Open Watcom C/16, small model, explicit cdecl at every ASM boundary. */
typedef unsigned char rb_u8;
typedef unsigned short rb_u16;
typedef unsigned long rb_u32;

typedef char rb_check_u8[(sizeof(rb_u8) == 1) ? 1 : -1];
typedef char rb_check_u16[(sizeof(rb_u16) == 2) ? 1 : -1];
typedef char rb_check_u32[(sizeof(rb_u32) == 4) ? 1 : -1];
typedef char rb_check_int[(sizeof(int) == 2) ? 1 : -1];
typedef char rb_check_near[(sizeof(void *) == 2) ? 1 : -1];
typedef char rb_check_far[(sizeof(void __far *) == 4) ? 1 : -1];

void __cdecl rb_putc(rb_u16 character);
rb_u16 __cdecl rb_check_context(const rb_u16 *local);
rb_u16 __cdecl rb_far_read(const volatile rb_u16 __far *address);
rb_u32 __cdecl rb_asm_mix(rb_u32 value, rb_u16 increment);

#endif
