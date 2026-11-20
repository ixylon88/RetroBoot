#include "mbr_ata.h"
#include "mbr_floppy.h"
#include "mbr_original.h"
#include "bios_ui.h"
#include "rescue_file.h"
#include "rescue_text.h"
#include "mbr_compare.h"
#include "mbr_review_ui.h"
#include "mbr_console.h"

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

static void identity(const char *label, const char *capacity, const rb_ata_identity *disk)
{
    line(label);
    field(RB_RS_D_MODEL, disk->model, sizeof(disk->model));
    field(RB_RS_D_SERIAL, disk->serial, sizeof(disk->serial));
    print(capacity); print(" 0x");
    hex32(disk->sectors_high); hex32(disk->sectors_low); line("");
}

static int check_recovery(const rb_ata_enrollment *p, int writable)
{
    rb_ata_identity live;
    identity(RB_RS_D_REC_EXPECT, RB_RS_D_REC_CAP, &p->recovery);
    if (!rb_ata_identify_recovery(&live, writable)) { line(RB_RS_D_REC_ABSENT); return 0; }
    identity(RB_RS_D_REC_LIVE, RB_RS_D_REC_CAP, &live);
    if (!equal((const rb_u8 *)&p->recovery, (const rb_u8 *)&live, sizeof(live))) {
        line(RB_RS_D_REC_WRONG); return 0;
    }
    if (!rb_ata_recovery_label(p)) { line(RB_RS_D_REC_LABEL); return 0; }
    line("RECOVERY MATCH");
    return 1;
}

static rb_u16 choice(rb_u16 accept)
{
    rb_u16 key;
    do { key = rb_mbr_review_key(); } while (key != 27 && key != accept);
    return key;
}

rb_u16 __cdecl rb_mbr_target_run(rb_u16 drive)
{
    rb_ata_enrollment p;
    rb_ata_identity live;
    rb_mbr_original_io io;
    capture_medium carrier;
    rb_u8 sector[512];
    static const rb_u8 zero[16] = {0};
    rb_mbr_review_source source = {0};
    int second;
    rb_u16 rc, key = 0;
    line("RB ATA TARGET");
    if (rb_floppy_read(2879, sector, &drive) || !rb_ata_decode_enrollment(&p, sector)) {
        line(RB_RS_D_PROFILE); return 1;
    }
    second = p.recovery.sectors_low || p.recovery.sectors_high;
    if (!equal(p.witness_id, zero, 16)) {
        source.binding = &p.binding; source.witness_id = p.witness_id;
        source.matches = rb_ata_target_matches;
        source.read = rb_ata_read_mbr; source.disk = &p; source.ata_profile = sector;
        if (second) {
            source.matches = rb_ata_pair_matches;
            source.carrier_read = rb_ata_read_record; source.carrier_write = rb_ata_write_record;
        }
        line(second ? RB_RS_D_BOTH : RB_RS_D_MENU);
        line(RB_RS_D_FIRST);
        do { key = rb_mbr_review_key(); } while (key != 'P' && key != 'E' && key != 'R' && key != 'V' && key != 27);
        if (key == 27) { return 0; }
    }
    identity(RB_RS_D_EXPECT, RB_RS_A_SECTORS, &p.device);
    if (key != 'V') {
        if (!rb_ata_identify(&live)) { line(RB_RS_D_ABSENT); return 1; }
        identity(RB_RS_D_LIVE, RB_RS_A_SECTORS, &live);
        if (!equal((const rb_u8 *)&p.device, (const rb_u8 *)&live, sizeof(live))) {
            line(RB_RS_D_WRONG); return 1;
        }
        line("TARGET MATCH");
    }
    if (second && !check_recovery(&p, key == 'E' || key == 'R')) { return 1; }
    if (second && (key == 'E' || key == 'R')) {
        line(key == 'E' ? RB_RS_D_REC_FIRST : RB_RS_D_REC_REVIEW);
        if (choice(key) == 27) { return 0; }
    }
    if (key == 'P') { return 0; }
    if (key) { return rb_mbr_review_action(key, drive, &source); }
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
