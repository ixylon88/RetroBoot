#include "mbr_review_ui.h"
#include "original_fixture.h"
#include "rescue_text.h"

static const rb_u8 witness_id[16] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x63};

rb_u16 __cdecl rb_mbr_review_demo(rb_u16 boot_drive)
{
    rb_mbr_binding binding;
    rb_mbr_review_source source = {0};
    rb_u16 key;
    capture_binding(&binding);
    source.binding = &binding; source.witness_id = witness_id; source.read = read_target;
    line("RB MBR REVIEW");
    line(RB_RS_A_MENU);
    do { key = rb_mbr_review_key(); } while (key != 'R' && key != 'V' && key != 'E' && key != 27);
    return rb_mbr_review_action(key, boot_drive, &source);
}
