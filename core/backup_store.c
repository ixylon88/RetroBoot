/* Read the independent store through its enrolled IDE device and floppy witness. */
#include "backup_store.h"
#include "config.h"
#include "fingerprint.h"
#include "mbr_floppy.h"
#include "mbr_compare.h"
#include "rescue_file.h"

rb_u16 __cdecl rb_ata_source_read(rb_u32 lba, rb_u8 *out);
rb_u16 __cdecl rb_ata_store_read(rb_u16 lba, rb_u8 *out);

rb_backup_store rb_store;
static capture_medium floppy;

void rb_store_copy(rb_u8 *out, const rb_u8 *in, rb_u16 size)
{
    while (size--) { *out++ = *in++; }
}

rb_u32 rb_store_get32(const rb_u8 *p)
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
    return rb_ata_recovery_label(&rb_store.profile);
}

static int layout(void)
{
    return endpoint() && !rb_ata_store_read(STORE_LAYOUT, rb_store.block)
        && equal(rb_store.block, (const rb_u8 *)"RBSTORE1", 8)
        && equal(rb_store.block + 8, rb_store.profile.binding.target.id, 16)
        && equal(rb_store.block + 24, rb_store.profile.binding.recovery_id, 16)
        && equal(rb_store.block + 40, rb_store.profile.witness_id, 16)
        && rb_store_get32(rb_store.block + 56) == rb_store.limit && rb_store.limit && rb_store.limit <= RB_BACKUP_SECTORS
        && (rb_store.profile.recovery.sectors_high || rb_store.profile.recovery.sectors_low >= STORE_DATA + rb_store.limit)
        && zero(rb_store.block + 60, 448) && rb_store_get32(rb_store.block + 508) == rb_crc32(rb_store.block, 508);
}

static int writable(void)
{
    rb_ata_identity actual;
    return layout() && rb_ata_identify_recovery(&actual, 1)
        && equal((const rb_u8 *)&actual, (const rb_u8 *)&rb_store.profile.recovery, sizeof(actual));
}

int rb_store_empty_slot(void)
{
    return writable() && !rb_ata_store_read(STORE_COMMIT, rb_store.block) && zero(rb_store.block, 512);
}

static rb_u16 __cdecl source_id(rb_mbr_target *actual, void *opaque)
{
    rb_rescue_device fresh;
    (void)opaque;
    if (!rb_ata_target_matches(&rb_store.profile) || rb_rescue_probe(&fresh) || !fresh.mode
        || !equal((const rb_u8 *)&fresh, (const rb_u8 *)&rb_store.source.device, sizeof(fresh))
        || fresh.capacity_low != rb_store.profile.device.sectors_low || fresh.capacity_high != rb_store.profile.device.sectors_high) {
        return 1;
    }
    *actual = rb_store.profile.binding.target;
    return 0;
}

static rb_u16 __cdecl live_read(rb_u32 pos, rb_u8 *out, void *opaque)
{
    (void)opaque;
    /* BIOS drive 80h and the enrolled physical primary IDE master must return the same bytes. */
    return rb_disk_read(pos, out, (void *)0) || rb_ata_source_read(pos, rb_store.block) || !equal(out, rb_store.block, 512);
}

rb_u16 __cdecl rb_store_file_read(rb_u32 pos, rb_u8 *out, void *opaque)
{
    (void)opaque;
    return pos >= rb_store.sectors || rb_store.sectors > rb_store.limit || !endpoint()
        || rb_ata_store_read((rb_u16)(STORE_DATA + pos), out);
}

int rb_store_history_valid(void)
{
    return !rb_mbr_load_witness(&rb_store.witness, &rb_store.profile.binding, rb_store.profile.witness_id, &rb_store.history.witness)
        && rb_store.witness.commit.approved && !rb_mbr_verify_carrier(&rb_store.witness, &rb_store.history.carrier);
}

void rb_store_make_commit(rb_u8 *out, const rb_u32 digest[2])
{
    clear(out, 512);
    rb_store_copy(out, (const rb_u8 *)"RBDONE01", 8);
    rb_store_copy(out + 8, rb_store.profile.binding.target.id, 16);
    rb_store_copy(out + 24, rb_store.profile.binding.recovery_id, 16);
    rb_store_copy(out + 40, rb_store.profile.witness_id, 16);
    put(out + 56, rb_store.sectors);
    put(out + 60, rb_store.witness.commit.generation);
    put(out + 64, rb_store.witness.commit.approved);
    put(out + 68, digest[0]); put(out + 72, digest[1]); put(out + 508, rb_crc32(out, 508));
}

/* Accept a published record only after a fresh physical read of the entire file,
   both exact MBRs, the independent witness, the carrier and the publication record. */
const rb_backup *rb_store_verify(void)
{
    rb_backup_boot boot;
    const rb_backup *saved;
    rb_u32 i, digest[2];
    if (!layout() || rb_ata_store_read(STORE_COMMIT, rb_store.metadata)) { return 0; }
    if (!equal(rb_store.metadata, (const rb_u8 *)"RBDONE01", 8)
        || rb_store_get32(rb_store.metadata + 508) != rb_crc32(rb_store.metadata, 508)) { return 0; }
    rb_store.sectors = rb_store_get32(rb_store.metadata + 56);
    if (!rb_store.sectors || rb_store.sectors > rb_store.limit || !rb_store_history_valid()) { return 0; }
    saved = rb_backup_open_boot(&boot, rb_store_file_read, (void *)0, rb_store.sectors);
    if (!saved || saved->capacity_low != rb_store.profile.device.sectors_low
        || saved->capacity_high != rb_store.profile.device.sectors_high || saved->generation != 1) { return 0; }
    digest[0] = digest[1] = 0;
    for (i = 0; i < rb_store.sectors; ++i) {
        if (rb_store_file_read(i, rb_store.block, (void *)0)
            || (i == saved->entries[0].file_sector && !equal(rb_store.block, rb_store.witness.original, 512))
            || (i == saved->entries[1].file_sector && !equal(rb_store.block, rb_store.witness.approved, 512))) { return 0; }
        rb_fingerprint_sector(digest, i, rb_store.block);
    }
    rb_store_make_commit(rb_store.block, digest);
    if (!equal(rb_store.block, rb_store.metadata, 512) || rb_mbr_verify_carrier(&rb_store.witness, &rb_store.history.carrier)
        || rb_mbr_verify_witness(&rb_store.witness, rb_store.profile.witness_id, &rb_store.history.witness)) { return 0; }
    if (!layout() || rb_ata_store_read(STORE_COMMIT, rb_store.block)
        || !equal(rb_store.block, rb_store.metadata, 512) || !endpoint()) { return 0; }
    return saved;
}

int rb_store_open(rb_u16 drive)
{
    if (rb_floppy_read(2879, rb_store.block, &drive) || !rb_ata_decode_enrollment(&rb_store.profile, rb_store.block)
        || !endpoint() || rb_ata_store_read(STORE_LAYOUT, rb_store.block)) { return RB_STORE_INVALID; }
    rb_store.limit = rb_store_get32(rb_store.block + 56);
    if (!layout() || rb_ata_store_read(STORE_COMMIT, rb_store.block)) { return RB_STORE_INVALID; }
    floppy.drive = drive;
    floppy.base = 2874; floppy.sectors = 4; floppy.id = rb_store.profile.witness_id;
    rb_store.history.binding = &rb_store.profile.binding; rb_store.history.witness_id = rb_store.profile.witness_id;
    rb_store.history.witness.read = rb_mbr_floppy_read; rb_store.history.witness.opaque = &floppy;
    rb_store.history.carrier.read = rb_ata_read_record; rb_store.history.carrier.opaque = &rb_store.profile;
    rb_store.source.read = live_read; rb_store.source.identify = source_id;
    return zero(rb_store.block, 512) ? RB_STORE_EMPTY : RB_STORE_OCCUPIED;
}

int rb_store_probe_source(void)
{
    rb_mbr_target id;
    return !rb_rescue_probe(&rb_store.source.device) && !source_id(&id, (void *)0);
}
