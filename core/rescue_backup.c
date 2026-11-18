#include "fingerprint.h"
#include "backup_live.h"
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

/* The validated file contains two separate one-sector MBR descriptors. */
static rb_u16 __cdecl saved_mbr(rb_u16 kind, rb_u16 index, rb_u32 offset,
    rb_u8 *out, void *opaque)
{
    const rb_backup *claims = (const rb_backup *)opaque;
    if ((kind != RB_BACKUP_ORIGINAL && kind != RB_BACKUP_APPROVED) || index || offset) { return 1; }
    return rb_rescue_file_read(claims->entries[kind - RB_BACKUP_ORIGINAL].file_sector, out, &file);
}

static rb_u16 __cdecl compare_sector(rb_u32 pos, const rb_u8 *data, void *opaque)
{
    rb_u8 reference[512];
    rb_u16 i;
    if (rb_rescue_file_read(pos, reference, opaque)) { return 1; }
    for (i = 0; i < sizeof(reference); ++i) {
        if (reference[i] != data[i]) { return 1; }
    }
    return 0;
}

static void compare(rb_u16 boot, rb_rescue_match *r, rb_u16 stream)
{
    rb_backup_live_result live;
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
    /* Each invocation opens its own BIOS observation. */
    code = rb_rescue_probe(&r->device);
    if (code) { fail(r, RB_RMATCH_PROBE, code, 0, 0, 0, 0); goto done; }
    if (stream) {
        rb_backup_live_stream(&live, claims, file.sectors, &r->device, rb_disk_read, (void *)0,
            saved_mbr, (void *)claims, compare_sector, &file);
        if (file_failure(r)) { goto done; }
        if (live.status) {
            fail(r, RB_RMATCH_LIVE, live.status, live.detail, live.capture_status,
                 live.stream.file_sector, live.error_lba);
            goto done;
        }
    } else {
        rb_backup_match_target(&r->observed, claims, &r->device, rb_disk_read, (void *)0);
        if (r->observed.status) {
            fail(r, RB_RMATCH_TARGET, r->observed.status, r->observed.detail, 0, 0, r->observed.error_lba);
            goto done;
        }
    }
    code = rb_rescue_probe(&after);
    if (code) { fail(r, stream ? RB_RMATCH_REPROBE : RB_RMATCH_PROBE, code, 0, 0, 0, 0); goto done; }
    for (i = 0; i < sizeof(after); ++i) {
        if (((const rb_u8 *)&after)[i] != ((const rb_u8 *)&r->device)[i]) {
            fail(r, RB_RMATCH_CHANGED, 1, 0, 0, 0, 0); goto done;
        }
    }
    /* Revalidate all saved content after HDD access, not just its FAT map. */
    if (!check_saved(r)) { goto done; }
    if (count != reads || before[0] != digest[0] || before[1] != digest[1]) {
        fail(r, RB_RMATCH_CHANGED, 2, 0, 0, 0, 0);
    } else if (stream) {
        r->verified_sectors = (rb_u16)live.stream.sectors; /* File limit is 2,048 sectors. */
    }
done:
    close_file(); digest[0] = digest[1] = 0; reads = 0;
}

void rb_rescue_backup_match(rb_u16 boot, rb_rescue_match *r)
{
    compare(boot, r, 0);
}

void rb_rescue_stream_check(rb_u16 boot, rb_rescue_match *r)
{
    compare(boot, r, 1);
}
