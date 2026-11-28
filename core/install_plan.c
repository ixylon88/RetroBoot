/* Read-only BIOS installer preview. */
#include "install_layout.h"
#include "mbr_console.h"
#include "mbr_compare.h"
#include "rescue_text.h"

static rb_install_snapshot shown, repeated;

static const char *observe(rb_install_snapshot *s, rb_u16 os, rb_u16 slot)
{
    const char *error = rb_install_observe(s, os, slot);
    return error ? error : rb_install_empty_boot(s, rb_disk_read);
}

static void blocked(const char *message, rb_u32 lba)
{
    rb_install_error(message, lba);
    line("RB INSTALL PLAN BLOCKED");
}

static rb_u16 choose(const char *prompt, rb_u16 first, rb_u16 last)
{
    rb_u16 key;
    line(prompt);
    do { key = rb_console_key(); } while (key != 27 && (key < first || key > last));
    return key;
}

rb_u16 __cdecl rb_install_plan_run(rb_u16 drive)
{
    rb_u16 os, slot;
    const char *error;
    (void)drive;
    line(RB_RS_IP_TITLE); line(RB_RS_IP_SCOPE);
    for (;;) {
        os = choose(RB_RS_IP_OS, '1', '3');
        if (os == 27) { return 0; }
        os -= '1';
        slot = choose(RB_RS_IP_SLOT, '1', '4');
        if (slot == 27) { continue; }
        slot -= '0';
        print(rb_install_systems[os]); print("  P"); rb_putc('0' + slot); line("");
        error = observe(&shown, os, slot);
        if (error) { blocked(error, shown.error_lba); continue; }
        rb_install_target(&shown);
        line(RB_RS_IP_BOOT_CLEAR); line(RB_RS_IP_VIEW);
        rb_install_render(repeated.tables, shown.tables, slot);
        rb_install_changes(shown.tables, repeated.tables);
        if (choose(RB_RS_IP_REPEAT, 'R', 'R') == 27) { continue; }
        error = observe(&repeated, os, slot);
        if (error || !equal((const rb_u8 *)&shown, (const rb_u8 *)&repeated, sizeof(shown))) {
            blocked(error ? error : RB_RS_IP_CHANGED, repeated.error_lba);
        } else { line("RB INSTALL PLAN VERIFIED"); }
    }
}
