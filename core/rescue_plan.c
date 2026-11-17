#include "rescue_plan.h"

static void clear(rb_backup_payloads *r)
{
    rb_u16 i;
    for (i = 0; i < sizeof(*r); ++i) { ((rb_u8 *)r)[i] = 0; }
}

rb_u16 rb_rescue_capture_payloads(rb_backup_payloads *r)
{
    rb_rescue_device before, after;
    rb_u16 code, i;
    clear(r);
    code = rb_rescue_probe(&before);
    if (code) { return code; }
    rb_backup_payload_capture(r, &before, rb_disk_read, (void *)0);
    if (r->plan.status) { return 0; }
    code = rb_rescue_probe(&after);
    if (code) { clear(r); return code; }
    for (i = 0; i < sizeof(after); ++i) {
        if (((const rb_u8 *)&before)[i] != ((const rb_u8 *)&after)[i]) {
            clear(r); r->plan.status = RB_CAPTURE_CHANGED; r->plan.detail = 1; break;
        }
    }
    return 0;
}
