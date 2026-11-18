#include "mbr_restart.h"
#include "rescue_file.h"
#include "bios_ui.h"
#include "config.h"

/* The boot floppy owns a four-sector fixture file at its final four LBAs.
   The exchanged, nonbootable data floppy has a label and six record sectors. */
typedef struct {
    rb_u16 base, length;
    rb_u8 endpoint[16], sample[6][512];
} test_disk;

static test_disk boot, recovery;
static rb_mbr_witness witness, trial;
static rb_mbr_recovered history;
static rb_mbr_binding binding;
static const rb_u8 witness_id[16] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x33};
static rb_u16 drive, calls, bad_at, fault;

#include "mbr_fixture.h"

static rb_u16 __cdecl bios_read(rb_u16 n, rb_u8 *out, rb_u8 *id, void *opaque)
{
    test_disk *disk = (test_disk *)opaque;
    rb_u8 label[512], closing[512];
    rb_u32 crc;
    rb_u16 i;
    if (n >= disk->length || rb_floppy_read(disk->base, label, &drive)) { return 0; }
    crc = rb_crc32(label, 508);
    if (!same(label, (const rb_u8 *)"RBMEDIA1", 8) || !empty(label + 24, 484)) { return 0; }
    for (i = 0; i < 4; ++i) {
        if (label[508 + i] != (rb_u8)(crc >> (8 * i))) { return 0; }
    }
    if (rb_floppy_read(disk->base + 1 + n, out, &drive)
        || rb_floppy_read(disk->base, closing, &drive) || !same(label, closing, 512)) { return 0; }
    copy(id, label + 8, 16);
    copy(disk->endpoint, id, 16);
    copy(disk->sample[n], out, 512);
    return 512;
}

static rb_u16 __cdecl replay_read(rb_u16 n, rb_u8 *out, rb_u8 *id, void *opaque)
{
    test_disk *disk = (test_disk *)opaque;
    if (n >= disk->length) { return 0; }
    copy(out, disk->sample[n], 512);
    copy(id, disk->endpoint, 16);
    if (++calls == bad_at) {
        rb_u16 i;
        rb_u32 crc;
        switch (fault) {
        case 0: return 0;
        case 1: return 511;
        case 2: return 513;
        case 3: id[0] ^= 1; break;
        case 4: out[77] ^= 1; break;
        case 5:
            crc = rb_crc32(out, 428);
            out[77] ^= 1;
            crc ^= rb_crc32(out, 428);
            for (i = 0; i < 4; ++i) { out[428 + i] ^= (rb_u8)(crc >> (8 * i)); }
            break;
        }
    }
    return 512;
}

/* Reuse the real, freshly acquired sectors in RAM to interrupt every read
   of each pass. Pre-populated destinations must lose all trust on failure. */
static int blocked_reads(const rb_mbr_recovered *accepted)
{
    rb_mbr_restart_source s;
    rb_u16 side, limit, rc;
    static rb_mbr_recovered failed;
    s.read = replay_read;
    for (side = 0; side < 2; ++side) {
        s.opaque = side ? &recovery : &boot;
        limit = side ? 8 : 6;
        for (bad_at = 1; bad_at <= limit; ++bad_at) {
            for (fault = 0; fault < 5; ++fault) {
                calls = 0;
                if (side) {
                    failed = *accepted;
                    rc = rb_mbr_reopen(&failed, &witness, &s);
                    if (!empty(&failed, sizeof(failed))) { return 0; }
                } else {
                    trial = witness;
                    rc = rb_mbr_load_witness(&trial, &binding, witness_id, &s);
                    if (!empty(&trial, sizeof(trial))) { return 0; }
                }
                if (!rc || calls != bad_at || (fault < 3 && rc != RB_REOPEN_IO)
                    || (fault == 3 && rc != RB_REOPEN_BINDING)) { return 0; }
            }
        }
    }
    /* The closing original now has a valid, identical whole-sector CRC. */
    s.opaque = &boot; calls = 0; bad_at = 5; fault = 5;
    rc = rb_mbr_load_witness(&trial, &binding, witness_id, &s);
    return rc == RB_REOPEN_CHANGED && calls == bad_at && empty(&trial, sizeof(trial));
}

static int exact_result(void)
{
    return same((const rb_u8 *)&history.binding, (const rb_u8 *)&binding, sizeof(binding))
        && same(history.original, witness.original, 512) && same(history.approved, witness.approved, 512)
        && history.generation == witness.commit.generation && history.issued == witness.commit.issued
        && history.approved_revision == witness.commit.approved;
}

static rb_u16 blocked(rb_u16 rc)
{
    static const char *const reasons[] = {
        "", "MISSING WITNESS", "MEDIA READ FAILED", "WRONG ENDPOINT",
        "INVALID RECORD", "INVALID CRC", "STALE CHECKPOINT", "EVIDENCE CHANGED"
    };
    if (rc >= sizeof(reasons) / sizeof(reasons[0])) { return 2; }
    line(reasons[rc]); return 1;
}

rb_u16 __cdecl rb_mbr_restart_demo(rb_u16 boot_drive)
{
    rb_mbr_restart_source s;
    rb_u16 rc, key;
    drive = boot_drive;
    boot.base = 2876; boot.length = 3; recovery.length = 6;
    binding.target.id[15] = 0x11; binding.recovery_id[15] = 0x22;
    binding.target.capacity_low = 262144UL; binding.target.capacity_high = 1;
    s.read = bios_read; s.opaque = &boot;
    line("RB MBR RESTART");
    rc = rb_mbr_load_witness(&witness, &binding, witness_id, &s);
    if (rc) { return blocked(rc); }
    line("WITNESS READY");
    line("INSERT RECOVERY FLOPPY AND PRESS ENTER");
    do {
        key = rb_key_poll();
        if (key == 0xffff) { rb_idle(); }
    } while ((key & 255) != 13);
    s.opaque = &recovery;
    rc = rb_mbr_reopen(&history, &witness, &s);
    if (rc) { return empty(&history, sizeof(history)) ? blocked(rc) : 2; }
    if (!blocked_reads(&history) || !exact_result()) { return 2; }
    line("ORIGINAL REV 1");
    if (history.approved_revision) { count("APPROVED REV ", history.approved_revision); }
    else { line("APPROVED NONE"); }
    count("LAST ISSUED ", history.issued);
    line("PENDING NONE");
    return 0;
}
