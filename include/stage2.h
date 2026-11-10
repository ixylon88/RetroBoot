#ifndef RB_STAGE2_H
#define RB_STAGE2_H

#include "abi.h"

/* Copied by startup from the MBR's context; no pointers into loader scratch. */
typedef struct {
    rb_u16 drive;
    rb_u16 io_mode;                 /* 0 = CHS, 1 = EDD */
    rb_u32 reachable_sectors_low;
    rb_u32 reachable_sectors_high;  /* AH=48 capacity or AH=08 CHS reach */
} rb_boot_context;

typedef char rb_check_boot_context[(sizeof(rb_boot_context) == 12) ? 1 : -1];

extern rb_boot_context rb_boot;
rb_u16 __cdecl rb_main(const rb_boot_context *boot);
rb_u32 __cdecl rb_c_mix(rb_u32 value, rb_u16 increment);

#endif
