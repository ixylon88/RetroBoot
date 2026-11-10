#include "handoff.h"
#include "stage2.h"
#include "handoff_fixture.h"

rb_u16 __cdecl rb_run_handoff_test(rb_u16 *detail)
{
    rb_handoff_buffer prepared;
    rb_handoff_target target;
    target.disk_id = RB_TEST_DISK_ID;
    target.slot = 1;
    target.entry = rb_test_entry;
    target.sector = rb_test_vbr;
    rb_prepare_handoff(&prepared, &target, rb_disk_read, (void *)0,
                      rb_boot.reachable_sectors_low, rb_boot.reachable_sectors_high);
    *detail = prepared.detail;
    if (prepared.status == RB_HANDOFF_OK) { rb_handoff(&prepared); }
    return prepared.status;
}
