/* First publication on an explicitly provisioned, independent secondary IDE disk. */
#include "backup_verify.h"
#include "backup_boot.h"
#include "config.h"
#include "fingerprint.h"
#include "mbr_ata.h"
#include "mbr_console.h"
#include "mbr_floppy.h"
#include "mbr_compare.h"
#include "rescue_file.h"
#include "rescue_text.h"

enum { STORE_LAYOUT = 7, STORE_COMMIT = 8, STORE_DATA = 16 };
rb_u16 __cdecl rb_ata_source_read(rb_u32 lba, rb_u8 *out);
rb_u16 __cdecl rb_ata_store_read(rb_u16 lba, rb_u8 *out);
rb_u16 __cdecl rb_ata_store_write(rb_u16 lba, const rb_u8 *in);

/* Headers on disk are encoded at explicit byte offsets, in little endian. */
static rb_ata_enrollment profile;
static rb_mbr_witness witness;
static rb_u8 block[512], metadata[512];
static rb_u32 limit, sectors, written, digest[2];
static rb_u16 drive;
static rb_backup_input source;
static rb_backup_history history;

static void copy(rb_u8 *out, const rb_u8 *in, rb_u16 size)
{
    while (size--) { *out++ = *in++; }
}

static rb_u32 get(const rb_u8 *p)
{
    return p[0] | ((rb_u32)p[1] << 8) | ((rb_u32)p[2] << 16) | ((rb_u32)p[3] << 24);
}

static void put(rb_u8 *p, rb_u32 n)
{
    rb_u16 i;
    for (i = 0; i < 4; ++i) { p[i] = (rb_u8)n; n >>= 8; }
}

static int zero(const rb_u8 *p, rb_u16 n)
{
    while (n--) { if (*p++) { return 0; } }
    return 1;
}

static int endpoint(void)
{
    /* Re-identify the hardware and independent carrier label on each access. */
    return rb_ata_recovery_label(&profile);
}

static int layout(void)
{
    return endpoint() && !rb_ata_store_read(STORE_LAYOUT, block)
        && equal(block, (const rb_u8 *)"RBSTORE1", 8)
        && equal(block + 8, profile.binding.target.id, 16)
        && equal(block + 24, profile.binding.recovery_id, 16)
        && equal(block + 40, profile.witness_id, 16)
        && get(block + 56) == limit && limit && limit <= RB_BACKUP_SECTORS
        && (profile.recovery.sectors_high || profile.recovery.sectors_low >= STORE_DATA + limit)
        && zero(block + 60, 448) && get(block + 508) == rb_crc32(block, 508);
}

static int writable(void)
{
    rb_ata_identity actual;
    return layout() && rb_ata_identify_recovery(&actual, 1)
        && equal((const rb_u8 *)&actual, (const rb_u8 *)&profile.recovery, sizeof(actual));
}

static int empty_slot(void)
{
    return writable() && !rb_ata_store_read(STORE_COMMIT, block) && zero(block, 512);
}

static rb_u16 __cdecl source_id(rb_mbr_target *actual, void *opaque)
{
    rb_rescue_device fresh;
    (void)opaque;
    if (!rb_ata_target_matches(&profile) || rb_rescue_probe(&fresh) || !fresh.mode
        || !equal((const rb_u8 *)&fresh, (const rb_u8 *)&source.device, sizeof(fresh))
        || fresh.capacity_low != profile.device.sectors_low || fresh.capacity_high != profile.device.sectors_high) {
        return 1;
    }
    *actual = profile.binding.target;
    return 0;
}

static rb_u16 __cdecl live_read(rb_u32 pos, rb_u8 *out, void *opaque)
{
    (void)opaque;
    /* BIOS drive 80h and the enrolled physical primary IDE master must return the same bytes. */
    return rb_disk_read(pos, out, (void *)0) || rb_ata_source_read(pos, block) || !equal(out, block, 512);
}

static rb_u16 __cdecl file_read(rb_u32 pos, rb_u8 *out, void *opaque)
{
    (void)opaque;
    return pos >= sectors || sectors > limit || !endpoint()
        || rb_ata_store_read((rb_u16)(STORE_DATA + pos), out);
}

static rb_u16 __cdecl stage(rb_u32 pos, const rb_u8 *in, void *opaque)
{
    (void)opaque;
    if (pos != written || pos >= sectors || sectors > limit || !empty_slot()
        || rb_ata_store_write((rb_u16)(STORE_DATA + pos), in)) { return 1; }
    rb_fingerprint_sector(digest, pos, in);
    ++written;
    return 0;
}

static rb_u16 __cdecl reopen(rb_u32 *bytes, void *opaque)
{
    (void)opaque;
    if (written != sectors || !empty_slot() || file_read(0, metadata, (void *)0)) { return 1; }
    *bytes = get(metadata + 12);
    return 0;
}

static int current_history(void)
{
    return !rb_mbr_load_witness(&witness, &profile.binding, profile.witness_id, &history.witness)
        && witness.commit.approved && !rb_mbr_verify_carrier(&witness, &history.carrier);
}

static rb_u32 collect(rb_backup *b)
{
    rb_backup_payloads capture;
    rb_backup_plan *p = &capture.plan;
    rb_u16 i;
    rb_u32 pos = 7;
    rb_backup_payload_capture(&capture, &source.device, live_read, (void *)0);
    if (p->status || !p->count || p->count >= RB_BACKUP_MAX) { return 0; }
    clear((rb_u8 *)b, sizeof(*b));
    b->generation = 1; /* This dedicated slot accepts one completed snapshot. */
    b->disk_id = p->observed.disk_id; b->layout_crc = p->observed.layout_crc;
    b->admin_start = p->observed.admin_start; b->admin_sectors = p->observed.admin_sectors;
    copy(b->media_id, p->observed.media_id, 16);
    b->capacity_low = p->device.capacity_low; b->capacity_high = p->device.capacity_high;
    b->count = p->count + 1; b->route = 1;
    b->heads = p->device.heads; b->sectors_per_track = p->device.sectors_per_track;
    for (i = 0; i < 2; ++i) {
        b->entries[i].kind = i + 1; b->entries[i].sectors = 1;
        b->entries[i].file_sector = 5 + i;
    }
    b->entries[0].crc = witness.commit.original_crc;
    b->entries[1].crc = witness.commit.approved_crc;
    for (i = 1; i < p->count; ++i) {
        const rb_capture_extent *live = &p->entries[i];
        rb_backup_extent *e = &b->entries[i + 1];
        e->kind = live->kind; e->index = live->index; e->lba = live->lba;
        e->owner_start = live->owner_start; e->owner_sectors = live->owner_sectors;
        e->sectors = live->sectors; e->file_sector = pos; e->crc = capture.crc[i]; pos += live->sectors;
    }
    return pos == p->estimated_container_sectors ? pos : 0;
}

static void make_commit(rb_u8 *out)
{
    clear(out, 512);
    copy(out, (const rb_u8 *)"RBDONE01", 8);
    copy(out + 8, profile.binding.target.id, 16); copy(out + 24, profile.binding.recovery_id, 16);
    copy(out + 40, profile.witness_id, 16);
    put(out + 56, sectors); put(out + 60, witness.commit.generation); put(out + 64, witness.commit.approved);
    put(out + 68, digest[0]); put(out + 72, digest[1]); put(out + 508, rb_crc32(out, 508));
}

/* Accept a published record only after a fresh physical read of the entire file,
   both exact MBRs, the independent witness, the carrier and the publication record. */
static int verify_saved(void)
{
    rb_backup_boot boot;
    const rb_backup *saved;
    rb_u32 i;
    if (!layout() || rb_ata_store_read(STORE_COMMIT, metadata)) { return 0; }
    if (!equal(metadata, (const rb_u8 *)"RBDONE01", 8) || get(metadata + 508) != rb_crc32(metadata, 508)) { return 0; }
    sectors = get(metadata + 56);
    if (!sectors || sectors > limit || !current_history()) { return 0; }
    saved = rb_backup_open_boot(&boot, file_read, (void *)0, sectors);
    if (!saved || saved->capacity_low != profile.device.sectors_low
        || saved->capacity_high != profile.device.sectors_high || saved->generation != 1) { return 0; }
    digest[0] = digest[1] = 0;
    for (i = 0; i < sectors; ++i) {
        if (file_read(i, block, (void *)0)
            || (i == saved->entries[0].file_sector && !equal(block, witness.original, 512))
            || (i == saved->entries[1].file_sector && !equal(block, witness.approved, 512))) { return 0; }
        rb_fingerprint_sector(digest, i, block);
    }
    make_commit(block);
    if (!equal(block, metadata, 512) || rb_mbr_verify_carrier(&witness, &history.carrier)
        || rb_mbr_verify_witness(&witness, profile.witness_id, &history.witness)) { return 0; }
    return layout() && !rb_ata_store_read(STORE_COMMIT, block) && equal(block, metadata, 512) && endpoint();
}

static int publish(void)
{
    rb_backup claims;
    static const rb_backup_destination destination = {stage, reopen, file_read, (void *)0};
    rb_backup_verified result;
    rb_mbr_target id;
    if (rb_rescue_probe(&source.device) || source_id(&id, (void *)0)) { line(RB_RS_STORE_SOURCE); return 0; }
    sectors = collect(&claims);
    if (!sectors) { line(RB_RS_STORE_SOURCE); return 0; }
    if (sectors > limit || !empty_slot()) { line(RB_RS_STORE_MEDIA); return 0; }
    written = digest[0] = digest[1] = 0;
    if (rb_backup_verify_live(&result, &claims, sectors, &source, &history, &destination)
        || result.sectors != sectors || result.approved_revision != witness.commit.approved
        || rb_mbr_verify_witness(&witness, profile.witness_id, &history.witness)
        || rb_mbr_verify_carrier(&witness, &history.carrier) || !empty_slot()) { return 0; }
    make_commit(metadata);
    if (rb_ata_store_write(STORE_COMMIT, metadata)) { return 0; }
    return verify_saved();
}

rb_u16 __cdecl rb_backup_disk_run(rb_u16 boot_drive)
{
    capture_medium floppy;
    rb_u16 key;
    drive = boot_drive;
    line("RB BACKUP DISK");
    line(RB_RS_STORE_MENU);
    do { key = rb_console_key(); } while (key != 'S' && key != 'V' && key != 27);
    if (key == 27) { line(RB_RS_STORE_CANCEL); return 0; }
    if (rb_floppy_read(2879, block, &drive) || !rb_ata_decode_enrollment(&profile, block)
        || !endpoint() || rb_ata_store_read(STORE_LAYOUT, block)) { line(RB_RS_STORE_MEDIA); return 1; }
    limit = get(block + 56);
    if (!layout() || rb_ata_store_read(STORE_COMMIT, block)) { line(RB_RS_STORE_MEDIA); return 1; }
    if (key == 'V' && zero(block, 512)) { line(RB_RS_STORE_EMPTY); return 1; }
    if (key == 'S' && !zero(block, 512)) { line(RB_RS_STORE_USED); return 1; }
    floppy.drive = drive; floppy.base = 2874; floppy.sectors = 4; floppy.id = profile.witness_id;
    history.binding = &profile.binding; history.witness_id = profile.witness_id;
    history.witness.read = rb_mbr_floppy_read; history.witness.opaque = &floppy;
    history.carrier.read = rb_ata_read_record; history.carrier.opaque = &profile;
    source.read = live_read; source.identify = source_id;
    line(key == 'S' ? RB_RS_STORE_SAVE : RB_RS_STORE_VERIFY);
    if (key == 'S' && !current_history()) { line(RB_RS_STORE_HISTORY); return 1; }
    if (!(key == 'S' ? publish() : verify_saved())) { line(RB_RS_STORE_FAILED); return 1; }
    line(key == 'S' ? RB_RS_STORE_DONE : RB_RS_STORE_READ);
    count(RB_RS_VERIFY_COUNT, sectors); count(RB_RS_STORE_REV, witness.commit.approved);
    return 0;
}
