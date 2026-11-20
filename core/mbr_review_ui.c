#include "mbr_review_ui.h"
#include "mbr_first_witness.h"
#include "mbr_approval.h"
#include "mbr_floppy.h"
#include "mbr_console.h"
#include "mbr_compare.h"
#include "rescue_file.h"
#include "bios_ui.h"
#include "rescue_text.h"

typedef struct {
    capture_medium medium;
    const rb_mbr_review_source *source;
    rb_u16 enrolling, saving, writing;
} review_drive;

rb_u16 rb_mbr_review_key(void)
{
    rb_u16 key;
    do {
        key = rb_key_poll();
        if (key == 0xffff) { rb_idle(); }
    } while (key == 0xffff);
    key &= 255;
    return key >= 'a' && key <= 'z' ? key - 'a' + 'A' : key;
}

static int witness_layout(review_drive *drive)
{
    static rb_rescue_file file;
    rb_u8 profile[512];
    capture_medium *m = &drive->medium;
    if (!drive->source->ata_profile) { return 1; }
    return !rb_floppy_read(2879, profile, &m->drive)
        && equal(profile, drive->source->ata_profile, 512)
        && rb_rescue_witness_extent(&file, rb_floppy_read, &m->drive, m->base, drive->writing);
}

static rb_u16 __cdecl select_medium(rb_u16 phase, void *opaque)
{
    review_drive *drive = (review_drive *)opaque;
    capture_medium *m = &drive->medium;
    rb_u16 key, carrier = phase == RB_MBR_SELECT_CARRIER;
    if (phase != RB_MBR_START_WITNESS && !drive->source->carrier_read) {
        if (carrier) { line(drive->saving ? RB_RS_A_SAVE_DATA : RB_RS_A_DATA); }
        else if (drive->source->ata_profile) { line(drive->saving ? RB_RS_D_SAVE_BACK : RB_RS_D_BACK); }
        else { line(drive->saving ? RB_RS_A_SAVE_BACK : RB_RS_A_BACK); }
        do { key = rb_mbr_review_key(); } while (key != 13 && key != 27);
        if (key == 27) { return 1; }
    }
    m->base = carrier ? 0 : (drive->source->ata_profile ? 2874 : 2875);
    m->sectors = carrier ? 6 : 4;
    m->id = carrier ? drive->source->binding->recovery_id : drive->source->witness_id;
    return !carrier && !witness_layout(drive);
}

static rb_u16 __cdecl read_record(rb_u16 n, rb_u8 *out, rb_u8 *id, void *opaque)
{
    review_drive *drive = (review_drive *)opaque;
    if (!drive->medium.base && drive->source->carrier_read) {
        return drive->source->carrier_read(n, out, id, drive->source->disk);
    }
    return rb_mbr_floppy_read(n, out, id, &drive->medium);
}

static rb_u16 __cdecl write_record(rb_u16 n, const rb_u8 *in, const rb_u8 *id, void *opaque)
{
    review_drive *drive = (review_drive *)opaque;
    capture_medium *m = &drive->medium;
    if (m->base) {
        if (n >= m->sectors || (drive->enrolling ? n > 1 : n == 1) || !witness_layout(drive)) { return 0; }
    } else {
        if (n >= m->sectors || (drive->enrolling && n > 2)) { return 0; }
        if (n < 2 && !(drive->enrolling && drive->source->ata_profile)) { return 0; }
    }
    if (drive->source->matches && !drive->source->matches(drive->source->disk)) { return 0; }
    if (!m->base && drive->source->carrier_read) {
        if (!drive->source->carrier_write) { return 0; }
        return drive->source->carrier_write(n, in, id, drive->source->disk);
    }
    if (!equal(m->id, id, 16) || !rb_mbr_floppy_matches(m)
        || rb_fixture_floppy_write(m->base + 1 + n, in, &m->drive) || !rb_mbr_floppy_matches(m)) { return 0; }
    return 512;
}

static void hexbyte(rb_u16 value)
{
    static const char digits[] = "0123456789ABCDEF";
    rb_putc(digits[(value >> 4) & 15]); rb_putc(digits[value & 15]);
}

static void show_id(const char *label, const rb_u8 *bytes)
{
    rb_u16 i;
    print(label);
    for (i = 0; i < 16; ++i) { rb_putc(' '); hexbyte(bytes[i]); }
    line("");
}

static void hexlong(rb_u32 value)
{
    hexbyte(value >> 24); hexbyte(value >> 16);
    hexbyte(value >> 8); hexbyte(value);
}

static rb_u16 __cdecl review(const rb_mbr_witness *old, const rb_u8 *candidate, void *opaque)
{
    review_drive *drive = (review_drive *)opaque;
    const rb_u8 *base = old->commit.approved ? old->approved : old->original;
    rb_u16 n, changes = 0, shown = 0, key;
    for (n = 0; n < 512; ++n) { if (base[n] != candidate[n]) { ++changes; } }
    show_id(RB_RS_A_TARGET, old->binding.target.id);
    show_id(RB_RS_A_CARRIER, old->binding.recovery_id);
    print(RB_RS_A_SECTORS); print(" 0x");
    hexlong(old->binding.target.capacity_high); hexlong(old->binding.target.capacity_low); line("");
    count("REVIEW ", old->commit.issued);
    count("BASE REV ", old->commit.approved ? old->commit.approved : 1);
    count("CHANGED BYTES ", changes);
    if (changes) { line(RB_RS_A_DIFF); }
    for (n = 0; n < 512; ++n) {
        if (base[n] == candidate[n]) { continue; }
        print("0x"); hexbyte(n >> 8); hexbyte(n); print("     ");
        hexbyte(base[n]); print(" -> "); hexbyte(candidate[n]); line("");
        if (++shown % 8 == 0 && shown < changes) {
            line(RB_RS_A_NEXT);
            do { key = rb_mbr_review_key(); } while (key != 'N' && key != 27);
            if (key == 27) { return RB_MBR_REJECT; }
        }
    }
    line(RB_RS_A_DECIDE);
    do { key = rb_mbr_review_key(); } while (key != RB_RS_A_YES[0] && key != 27);
    if (key == 27) { return RB_MBR_REJECT; }
    drive->saving = 1;
    return RB_MBR_APPROVE;
}

static rb_u16 verify(const rb_mbr_binding *binding, review_drive *drive)
{
    rb_mbr_witness witness;
    rb_mbr_recovered records;
    rb_mbr_restart_source source;
    rb_u16 rc;
    source.read = read_record; source.opaque = drive;
    if (select_medium(RB_MBR_START_WITNESS, drive)) { return RB_REOPEN_IO; }
    rc = rb_mbr_load_witness(&witness, binding, drive->source->witness_id, &source);
    if (rc) { return rc; }
    if (select_medium(RB_MBR_SELECT_CARRIER, drive)) { return RB_REOPEN_IO; }
    rc = rb_mbr_reopen(&records, &witness, &source);
    if (rc) { return rc; }
    line("ORIGINAL REV 1 VERIFIED");
    if (records.approved_revision) { count("APPROVED REV ", records.approved_revision); }
    else { line("APPROVED NONE"); }
    count("LAST ISSUED ", records.issued);
    return 0;
}

rb_u16 rb_mbr_review_action(rb_u16 key, rb_u16 boot_drive, const rb_mbr_review_source *source)
{
    rb_mbr_exchange media;
    review_drive drive = {0};
    rb_u32 approved;
    rb_u16 rc;
    drive.medium.drive = boot_drive;
    drive.source = source;
    drive.writing = key == 'R' || key == 'E';
    media.read = read_record; media.write = write_record;
    media.select = select_medium; media.opaque = &drive;
    if (key == 'V') { rc = verify(source->binding, &drive); }
    else if (key == 'R') {
        rc = rb_mbr_publish_review(&approved, source->binding, source->witness_id, source->read,
                                   source->disk, &media, review, &drive);
        if (!rc) { count("APPROVED REV ", approved); }
        if (rc == RB_APPROVAL_REJECTED && !approved) { line("REVIEW REJECTED"); return 0; }
    } else if (key == 'E') {
        drive.enrolling = 1;
        if (source->ata_profile) {
            rc = rb_mbr_capture_first_witness(source->binding, source->witness_id, RB_MBR_FIRST_INSTALL,
                                              source->read, source->disk, &media);
        } else {
            rc = rb_mbr_publish_first_witness(source->binding, source->witness_id, RB_MBR_FIRST_INSTALL,
                                              source->read, source->disk, &media);
        }
        if (!rc) { line("INITIAL WITNESS PUBLISHED"); }
    } else { line("REVIEW CANCELLED"); return 0; }
    if (rc) { count("REVIEW STATUS ", rc); return 1; }
    return 0;
}
