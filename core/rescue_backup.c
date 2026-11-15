#include "fingerprint.h"
#include "rescue_file.h"
#include "rescue_match.h"
#include "config.h"

static rb_rescue_file file;
static rb_u32 digest[2];
static rb_u16 reads;

static void clear(void *p, rb_u16 size)
{
    rb_u8 *bytes = (rb_u8 *)p;
    while (size) { bytes[--size] = 0; }
}
static void close_file(void)
{
    file.ready = 0; file.read = (rb_sector_reader)0; file.opaque = (void *)0;
}

void rb_rescue_backup_check(rb_u16 boot, rb_u16 *status, rb_u32 *lba, rb_backup_boot *result)
{
    rb_u16 i;
    for (i = 0; i < sizeof(*result); ++i) { ((rb_u8 *)result)[i] = 0; }
    rb_rescue_file_open(&file, rb_floppy_read, &boot);
    if (!file.status) {
        rb_backup_check_boot(result, rb_rescue_file_read, &file, file.sectors);
        if (!file.status && !result->status) { rb_rescue_file_recheck(&file); }
    }
    *status = file.status; *lba = file.error_lba;
    if (file.status) {
        for (i = 0; i < sizeof(*result); ++i) { ((rb_u8 *)result)[i] = 0; }
    }
    /* The caller's boot-drive pointer is valid only during this operation. */
    close_file();
}

/* File-relative addresses never become HDD read addresses. */
static rb_u16 __cdecl saved_read(rb_u32 sector, rb_u8 *out, void *opaque)
{
    if (rb_rescue_file_read(sector, out, opaque)) { return 1; }
    rb_fingerprint_sector(digest, sector, out);
    ++reads; return 0;
}
static void fail(rb_rescue_match *r, rb_u16 status, rb_u16 detail, rb_u16 nested,
                 rb_u16 record, rb_u32 file_lba, rb_u32 disk_lba)
{
    clear(r, sizeof(*r)); r->status = status; r->detail = detail;
    r->nested = nested; r->record_detail = record;
    r->file_lba = file_lba; r->disk_lba = disk_lba;
}
static rb_u16 file_failure(rb_rescue_match *r)
{
    if (!file.status) { return 0; }
    fail(r, RB_RMATCH_FILE, file.status, 0, 0, file.error_lba, 0); return 1;
}
static const rb_backup *check_saved(rb_rescue_match *r)
{
    rb_backup_boot result;
    const rb_backup *claims;
    reads = 0; digest[0] = digest[1] = 0;
    claims = rb_backup_open_boot(&result, saved_read, &file, file.sectors);
    if (file_failure(r)) { return (const rb_backup *)0; }
    if (!claims) {
        fail(r, RB_RMATCH_SAVED, result.status, result.detail, result.record_detail, 0, result.error_lba);
        return (const rb_backup *)0;
    }
    rb_rescue_file_recheck(&file);
    return file_failure(r) ? (const rb_backup *)0 : claims;
}

void rb_rescue_backup_match(rb_u16 boot, rb_rescue_match *r)
{
    const rb_backup *claims;
    rb_rescue_device after;
    rb_u32 before[2];
    rb_u16 i, count, code;
    clear(r, sizeof(*r));
    rb_rescue_file_open(&file, rb_floppy_read, &boot);
    if (file_failure(r)) { goto done; }
    claims = check_saved(r);
    if (!claims) { goto done; }
    before[0] = digest[0]; before[1] = digest[1]; count = reads;
    /* A prior Enter or F5 observation is never reused. */
    code = rb_rescue_probe(&r->device);
    if (code) { fail(r, RB_RMATCH_PROBE, code, 0, 0, 0, 0); goto done; }
    rb_backup_match_target(&r->observed, claims, &r->device, rb_disk_read, (void *)0);
    if (r->observed.status) {
        fail(r, RB_RMATCH_TARGET, r->observed.status, r->observed.detail, 0, 0, r->observed.error_lba);
        goto done;
    }
    code = rb_rescue_probe(&after);
    if (code) { fail(r, RB_RMATCH_PROBE, code, 0, 0, 0, 0); goto done; }
    for (i = 0; i < sizeof(after); ++i) {
        if (((const rb_u8 *)&after)[i] != ((const rb_u8 *)&r->device)[i]) {
            fail(r, RB_RMATCH_CHANGED, 1, 0, 0, 0, 0); goto done;
        }
    }
    /* Revalidate all saved content after HDD access, not just its FAT map. */
    if (!check_saved(r)) { goto done; }
    if (count != reads || before[0] != digest[0] || before[1] != digest[1]) {
        fail(r, RB_RMATCH_CHANGED, 2, 0, 0, 0, 0);
    }
done:
    close_file(); digest[0] = digest[1] = 0; reads = 0;
}
