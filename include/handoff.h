#ifndef RB_HANDOFF_H
#define RB_HANDOFF_H

#include "volume.h"

enum { RB_HANDOFF_OK, RB_HANDOFF_TARGET, RB_HANDOFF_SCAN,
       RB_HANDOFF_VOLUME, RB_HANDOFF_CODE };

typedef struct {
    rb_u8 sector[512], entry[16];
    rb_u16 status, detail;
} rb_handoff_buffer;
typedef char rb_check_handoff[(sizeof(rb_handoff_buffer) == 532) ? 1 : -1];

/* Test-only authorization: exact compiled fixture, never an OS boot profile. */
typedef struct {
    rb_u32 disk_id;
    rb_u16 slot;
    const rb_u8 *entry, *sector;
} rb_handoff_target;

rb_u16 rb_prepare_handoff(rb_handoff_buffer *result, const rb_handoff_target *target,
                         rb_sector_reader read, void *opaque, rb_u32 low, rb_u32 high);
void __cdecl rb_handoff(const rb_handoff_buffer *prepared);
rb_u16 __cdecl rb_run_handoff_test(rb_u16 *detail);
rb_u16 __cdecl rb_handoff_selftest(void);

#endif
