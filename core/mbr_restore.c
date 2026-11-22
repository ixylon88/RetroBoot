/* External recovery of the executable prefix of this build's Stage 1. */
#include "backup_store.h"
#include "backup_target.h"
#include "mbr_compare.h"
#include "mbr_console.h"
#include "rescue_text.h"
#include "restore_stage1.h"

rb_u16 __cdecl rb_ata_restore_mbr(const rb_u8 *sector);

enum { CODE_BYTES = sizeof(stage1_code) };
enum { RESTORE_BLOCKED, RESTORE_READY, RESTORE_INTACT };
typedef char check_code_size[(CODE_BYTES == 432) ? 1 : -1];

typedef struct {
    rb_ata_enrollment profile;
    rb_u8 publication[512], mbr[512];
} restore_plan;

static restore_plan shown, fresh;
static rb_u8 sector[512];

static int reject(const char *reason)
{
    line(reason);
    return RESTORE_BLOCKED;
}

static int same_source(void)
{
    rb_mbr_target id;
    return !rb_store.source.identify(&id, (void *)0);
}

static int read_live(rb_u32 lba, rb_u8 *out)
{
    return rb_store.source.read(lba, out, (void *)0) == 0;
}

/* Only a completely erased executable prefix is eligible. The live pointer
   and disk signature must bind the approved code to the same audited volume.
   Current partition flags, reserved bytes and geometry come from the target. */
static int inspect(rb_u16 drive, restore_plan *plan)
{
    rb_backup_target match;
    const rb_backup *saved;
    const rb_u8 *approved = rb_store.witness.approved;
    rb_u16 i;
    if (rb_store_open(drive) != RB_STORE_OCCUPIED || !(saved = rb_store_verify())) {
        return reject(RB_RS_RESTORE_BACKUP);
    }
    if (!rb_store_probe_source() || !rb_ata_target_can_flush(&rb_store.profile)
        || !read_live(0, plan->mbr)) { return reject(RB_RS_RESTORE_TARGET); }
    if (!equal(approved, stage1_code, CODE_BYTES)
        || !equal(approved + 432, (const rb_u8 *)"RBM1", 4)
        || rb_store_get32(approved + 436) != saved->admin_start
        || rb_store_get32(approved + 440) != saved->disk_id
        || approved[510] != 0x55 || approved[511] != 0xaa
        || !equal(plan->mbr + 432, approved + 432, 12)) { return reject(RB_RS_RESTORE_SCOPE_BAD); }

    /* Both GPT header locations must be readable through the fixed LBA28 route. */
    if (saved->capacity_high || saved->capacity_low < 3 || saved->capacity_low > 0x10000000UL
        || !read_live(1, sector) || equal(sector, (const rb_u8 *)"EFI PART", 8)
        || !read_live(saved->capacity_low - 1, sector) || equal(sector, (const rb_u8 *)"EFI PART", 8)) {
        return reject(RB_RS_RESTORE_TARGET);
    }
    rb_backup_match_target(&match, saved, &rb_store.source.device, rb_store.source.read, (void *)0);
    if (match.status || !same_source() || !read_live(0, sector)
        || !equal(sector, plan->mbr, 512)) { return reject(RB_RS_RESTORE_TARGET); }
    if (equal(plan->mbr, approved, CODE_BYTES)) { return RESTORE_INTACT; }
    for (i = 0; i < CODE_BYTES; ++i) {
        if (plan->mbr[i]) { return reject(RB_RS_RESTORE_SCOPE_BAD); }
    }
    plan->profile = rb_store.profile;
    rb_store_copy(plan->publication, rb_store.metadata, 512);
    return RESTORE_READY;
}

rb_u16 __cdecl rb_mbr_restore_run(rb_u16 drive)
{
    int status;
    rb_u16 key, n;
    line("RB MBR RESTORE");
    line(RB_RS_RESTORE_CHECK);
    status = inspect(drive, &shown);
    if (status == RESTORE_BLOCKED) { return 1; }
    if (status == RESTORE_INTACT) { line(RB_RS_RESTORE_INTACT); return 0; }

    print(RB_RS_D_SERIAL); rb_putc(' ');
    n = sizeof(shown.profile.device.serial);
    while (n && shown.profile.device.serial[n - 1] == ' ') { --n; }
    for (key = 0; key < n; ++key) { rb_putc(shown.profile.device.serial[key]); }
    line("");
    count(RB_RS_STORE_REV, rb_store.witness.commit.approved);
    line(RB_RS_RESTORE_SCOPE);
    line(RB_RS_RESTORE_KEEP);
    line(RB_RS_RESTORE_CONFIRM);
    do { key = rb_console_key(); } while (key != RB_RS_A_YES[0] && key != 27);
    if (key == 27) { line(RB_RS_RESTORE_CANCEL); return 0; }

    /* Re-open both media after the operator pause. Pin the exact enrollment,
       commit and original target sector that were used for the displayed plan. */
    status = inspect(drive, &fresh);
    if (status == RESTORE_BLOCKED) { return 1; }
    if (status != RESTORE_READY || !equal((const rb_u8 *)&fresh, (const rb_u8 *)&shown, sizeof(shown))
        || !rb_ata_target_can_flush(&fresh.profile) || !read_live(0, sector)
        || !equal(sector, fresh.mbr, 512)) { line(RB_RS_RESTORE_CHANGED); return 1; }

    rb_store_copy(fresh.mbr, rb_store.witness.approved, CODE_BYTES);
    if (rb_ata_restore_mbr(fresh.mbr) || !same_source() || !read_live(0, sector)
        || !equal(sector, fresh.mbr, 512) || !same_source()) {
        line(RB_RS_RESTORE_IO); return 1;
    }
    line(RB_RS_RESTORE_DONE);
    return 0;
}
