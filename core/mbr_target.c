#include "mbr_ata.h"
#include "mbr_floppy.h"
#include "mbr_original.h"
#include "bios_ui.h"
#include "rescue_file.h"
#include "rescue_text.h"
#include "mbr_compare.h"

static void print(const char *s)
{
    while (*s) { rb_putc(*s++); }
}

static void line(const char *s)
{
    print(s); rb_putc(13); rb_putc(10);
}

static void field(const char *label, const rb_u8 *s, rb_u16 len)
{
    print(label); rb_putc(' ');
    while (len && s[len - 1] == ' ') { --len; }
    while (len--) { rb_putc(*s++); }
    line("");
}

static void hex32(rb_u32 value)
{
    static const char digits[] = "0123456789ABCDEF";
    rb_u16 i;
    for (i = 0; i < 8; ++i) { rb_putc(digits[value >> 28]); value <<= 4; }
}

static void identity(const char *label, const rb_ata_identity *disk)
{
    line(label);
    field(RB_RS_D_MODEL, disk->model, sizeof(disk->model));
    field(RB_RS_D_SERIAL, disk->serial, sizeof(disk->serial));
    print(RB_RS_A_SECTORS); print(" 0x");
    hex32(disk->sectors_high); hex32(disk->sectors_low); line("");
}

static rb_u16 choice(rb_u16 accept)
{
    rb_u16 key;
    for (;;) {
        key = rb_key_poll();
        if (key == 0xffff) { rb_idle(); continue; }
        key &= 255;
        if (key >= 'a' && key <= 'z') { key -= 'a' - 'A'; }
        if (key == 27 || key == accept) { return key; }
    }
}

rb_u16 __cdecl rb_mbr_target_run(rb_u16 drive)
{
    rb_ata_enrollment p;
    rb_ata_identity live;
    rb_mbr_original_io io;
    capture_medium carrier;
    rb_u8 sector[512];
    rb_u16 rc;
    line("RB ATA TARGET");
    if (rb_floppy_read(2879, sector, &drive) || !rb_ata_decode_enrollment(&p, sector)) {
        line(RB_RS_D_PROFILE); return 1;
    }
    identity(RB_RS_D_EXPECT, &p.device);
    if (!rb_ata_identify(&live)) { line(RB_RS_D_ABSENT); return 1; }
    identity(RB_RS_D_LIVE, &live);
    if (!equal((const rb_u8 *)&p.device, (const rb_u8 *)&live, sizeof(live))) {
        line(RB_RS_D_WRONG); return 1;
    }
    line("TARGET MATCH");
    line(RB_RS_D_ACTION);
    if (choice('E') == 27) { return 0; }
    line(RB_RS_D_INSERT);
    if (choice(13) == 27) { line(RB_RS_D_CANCEL); return 0; }
    carrier.drive = drive; carrier.base = 0; carrier.sectors = 6;
    carrier.id = p.binding.recovery_id;
    io.current = rb_ata_read_mbr; io.disk = &p;
    io.read = rb_mbr_floppy_read; io.write = rb_mbr_floppy_save_original; io.carrier = &carrier;
    rc = rb_mbr_capture_original(&p.binding, RB_MBR_FIRST_INSTALL, &io);
    if (rc) {
        line(RB_RS_D_CAPTURE_FAIL);
        print("CAPTURE STATUS "); rb_putc('0' + rc); line("");
        return 1;
    }
    line("ORIGINAL REV 1 VERIFIED");
    return 0;
}
