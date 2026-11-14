#include "rescue_plan.h"

static void clear(rb_backup_plan *r)
{
    rb_u16 i;
    for (i = 0; i < sizeof(*r); ++i) { ((rb_u8 *)r)[i] = 0; }
}

rb_u16 rb_rescue_capture_plan(rb_backup_plan *r)
{
    rb_rescue_device before, after;
    rb_u16 code, i;
    clear(r);
    code = rb_rescue_probe(&before);
    if (code) { return code; }
    rb_backup_plan_capture(r, &before, rb_disk_read, (void *)0);
    if (r->status) { return 0; }
    code = rb_rescue_probe(&after);
    if (code) { clear(r); return code; }
    for (i = 0; i < sizeof(after); ++i) {
        if (((const rb_u8 *)&before)[i] != ((const rb_u8 *)&after)[i]) {
            clear(r); r->status = RB_CAPTURE_CHANGED; r->detail = 1; break;
        }
    }
    return 0;
}
