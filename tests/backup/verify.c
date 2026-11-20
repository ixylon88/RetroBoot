/* Bootable completion test. Only the provisional destination occupies extra RAM. */
#include "backup_verify.h"
#include "backup_boot.h"
#include "mbr_console.h"
#include "rescue_text.h"

typedef struct { rb_u32 sector; rb_u16 block; } sector_ref;
typedef struct { rb_u16 offset; rb_u8 value; } patch;
#include "backup_verify_vectors.h"

#define ITEMS(a) (sizeof(a)/sizeof((a)[0]))
enum { GOOD, WRONG_SOURCE, FOREIGN_CARRIER, NO_APPROVAL, STALE_CARRIER,
       LAST_WRITE, PRODUCER_CLOSE, OPEN_ERROR, TRUNCATED, SHORT_BYTE, EXTRA_BYTE,
       EXTRA_SECTOR, OVERLAP, LAST_DAMAGE, BAD_STATE, BAD_FAT, OTHER_ORIGINAL,
       OTHER_APPROVAL, OTHER_CONFIG, LAST_READ, LATE_READ, LATE_WITNESS, LATE_SOURCE,
       LATE_LENGTH, REOPEN_SUBSTITUTION, LONG_OUTPUT };

static const struct {
    rb_u16 mode, status, detail, writes, opens;
} cases[] = {
    {GOOD, RB_VERIFY_OK, 0, 45, 2},
    {WRONG_SOURCE, RB_VERIFY_TARGET, 0, 0, 0},
    {FOREIGN_CARRIER, RB_VERIFY_CARRIER, RB_REOPEN_BINDING, 0, 0},
    {NO_APPROVAL, RB_VERIFY_APPROVAL, 0, 0, 0},
    {STALE_CARRIER, RB_VERIFY_CARRIER, RB_REOPEN_STALE, 0, 0},
    {LAST_WRITE, RB_VERIFY_PRODUCER, RB_LIVE_STREAM, 45, 0},
    {PRODUCER_CLOSE, RB_VERIFY_PRODUCER, RB_LIVE_CAPTURE, 45, 0},
    {OPEN_ERROR, RB_VERIFY_OPEN, 0, 45, 1},
    {TRUNCATED, RB_VERIFY_LENGTH, 0, 45, 1},
    {SHORT_BYTE, RB_VERIFY_LENGTH, 0, 45, 1},
    {EXTRA_BYTE, RB_VERIFY_LENGTH, 0, 45, 1},
    {EXTRA_SECTOR, RB_VERIFY_LENGTH, 0, 45, 1},
    {OVERLAP, RB_VERIFY_SAVED, RB_BBOOT_RECORDS, 45, 1},
    {LAST_DAMAGE, RB_VERIFY_SAVED, RB_BBOOT_RECORDS, 45, 1},
    {BAD_STATE, RB_VERIFY_SAVED, RB_BBOOT_RECORDS, 45, 1},
    {BAD_FAT, RB_VERIFY_SAVED, RB_BBOOT_FSINFO, 45, 1},
    {OTHER_ORIGINAL, RB_VERIFY_DIFFER, 0, 45, 2},
    {OTHER_APPROVAL, RB_VERIFY_DIFFER, 0, 45, 2},
    {OTHER_CONFIG, RB_VERIFY_DIFFER, 0, 45, 2},
    {LAST_READ, RB_VERIFY_SAVED, RB_BBOOT_RECORDS, 45, 1},
    {LATE_READ, RB_VERIFY_READ, 0, 45, 2},
    {LATE_WITNESS, RB_VERIFY_WITNESS, RB_REOPEN_CHANGED, 45, 2},
    {LATE_SOURCE, RB_VERIFY_TARGET, 0, 45, 2},
    {LATE_LENGTH, RB_VERIFY_LENGTH, 0, 45, 2},
    {REOPEN_SUBSTITUTION, RB_VERIFY_DIFFER, 0, 45, 2},
    {LONG_OUTPUT, RB_VERIFY_OK, 0, LONG_SECTORS, 2},
    {GOOD, RB_VERIFY_OK, 0, 45, 2}
};
static rb_u16 mode, writes, opens, identities, file_sectors;
static rb_u16 disk_context, file_context, witness_context, carrier_context;
static rb_backup_verified result;

static void zero_sector(rb_u8 *out)
{
    rb_u16 i;
    for (i = 0; i < 512; ++i) { out[i] = 0; }
}

static void unpack(rb_u16 id, rb_u8 *out)
{
    rb_u16 i, first = spans[id][0], end = first + spans[id][1];
    zero_sector(out);
    for (i = first; i < end; ++i) { out[bytes[i].offset] = bytes[i].value; }
}

static rb_u16 __cdecl live_read(rb_u32 lba, rb_u8 *out, void *context)
{
    rb_u16 i;
    if (context != &disk_context || lba >= binding.target.capacity_low
        || (mode == PRODUCER_CLOSE && writes == file_sectors)) { return 1; }
    if (mode == LONG_OUTPUT) {
        for (i = 0; i < ITEMS(long_changes); ++i) {
            if (long_changes[i].sector == lba) { unpack(long_changes[i].block, out); return 0; }
        }
    }
    for (i = 0; i < ITEMS(source_sectors); ++i) {
        if (source_sectors[i].sector == lba) { unpack(source_sectors[i].block, out); return 0; }
    }
    zero_sector(out); return 0;
}

static rb_u16 __cdecl identify(rb_mbr_target *actual, void *context)
{
    if (context != &disk_context) { return 1; }
    ++identities;
    *actual = binding.target;
    if (mode == WRONG_SOURCE || (mode == LATE_SOURCE && identities == 3)) { actual->id[0] ^= 1; }
    return 0;
}

static rb_u16 __cdecl history_read(rb_u16 n, rb_u8 *out, rb_u8 *id, void *context)
{
    rb_u16 i, has_approval = mode != NO_APPROVAL;
    const rb_u8 *map, *endpoint;
    if (context == &witness_context && n < ITEMS(witness_approved)) {
        if (mode == LATE_WITNESS && opens) { has_approval = 0; }
        map = has_approval ? witness_approved : witness_original;
        endpoint = witness_id;
    } else if (context == &carrier_context && n < ITEMS(carrier_approved)) {
        map = (has_approval && mode != STALE_CARRIER) ? carrier_approved : carrier_original;
        endpoint = binding.recovery_id;
    } else { return 0; }
    for (i = 0; i < 16; ++i) { id[i] = endpoint[i]; }
    if (context == &carrier_context && mode == FOREIGN_CARRIER) { id[0] ^= 1; }
    unpack(map[n], out); return 512;
}

/* The fixture holds real sectors at physical 0x20000 (45) or 0x30000 (143), beyond the C/16
   runtime segment. Every byte read back came through the native sink. */
static rb_u8 __far *at(rb_u32 pos)
{
    return (rb_u8 __far *)(((mode == LONG_OUTPUT ? 0x3000UL : 0x2000UL) + pos * 32UL) << 16);
}

static rb_u16 __cdecl write_at(rb_u32 pos, const rb_u8 *in, void *context)
{
    rb_u16 i;
    rb_u8 __far *dest;
    if (context != &file_context || opens || pos != writes || pos >= file_sectors) { return 1; }
    dest = at(pos);
    for (i = 0; i < 512; ++i) { dest[i] = in[i]; }
    ++writes;
    return mode == LAST_WRITE && writes == file_sectors;
}

static void replace_blocks(const sector_ref *changes, rb_u16 count)
{
    rb_u16 i;
    rb_u8 block[512];
    rb_u8 __far *dest;
    while (count--) {
        unpack(changes->block, block); dest = at(changes->sector);
        for (i = 0; i < 512; ++i) { dest[i] = block[i]; }
        ++changes;
    }
}

static rb_u16 __cdecl reopen(rb_u32 *size, void *context)
{
    if (context != &file_context || writes != file_sectors) { return 1; }
    ++opens; *size = writes * 512UL;
    if (mode == OPEN_ERROR) { return 1; }
    if (mode == SHORT_BYTE) { --*size; }
    if (mode == EXTRA_BYTE || (mode == LATE_LENGTH && opens == 2)) { ++*size; }
    if (mode == EXTRA_SECTOR) { *size += 512; }
    if (mode == TRUNCATED) { *size -= 512; }
    if (opens == 2 && mode == REOPEN_SUBSTITUTION) { replace_blocks(sub_approved, ITEMS(sub_approved)); }
    if (opens == 1) {
        switch (mode) {
        case OVERLAP: replace_blocks(overlap, ITEMS(overlap)); break;
        case LAST_DAMAGE: at(FILE_SECTORS - 1)[511] ^= 1; break;
        case BAD_FAT: replace_blocks(boot_area, ITEMS(boot_area)); break;
        case BAD_STATE: replace_blocks(saved_state, ITEMS(saved_state)); break;
        case OTHER_ORIGINAL: replace_blocks(sub_original, ITEMS(sub_original)); break;
        case OTHER_APPROVAL: replace_blocks(sub_approved, ITEMS(sub_approved)); break;
        case OTHER_CONFIG: replace_blocks(changed_config, ITEMS(changed_config)); break;
        }
    }
    return 0;
}

static rb_u16 __cdecl read_at(rb_u32 pos, rb_u8 *out, void *context)
{
    rb_u16 i;
    const rb_u8 __far *src;
    if (context != &file_context || !opens || pos >= writes) { return 1; }
    if (pos == FILE_SECTORS - 1 && (mode == LAST_READ || (mode == LATE_READ && identities == 2))) { return 1; }
    src = at(pos);
    for (i = 0; i < 512; ++i) { out[i] = src[i]; }
    return 0;
}

rb_u16 __cdecl rb_backup_verify_selftest(void)
{
    static const rb_backup_input disk = {{0x80,1,0,0,262144UL,0}, live_read, identify, &disk_context};
    static const rb_backup_history history = {&binding, witness_id,
        {history_read, &witness_context}, {history_read, &carrier_context}};
    static const rb_backup_destination file = {write_at, reopen, read_at, &file_context};
    rb_u16 i, status;
    /* BIOS conventional memory in KiB must cover the complete fixture. */
    if (*(const rb_u16 __far *)0x00400013UL < 192U + (LONG_SECTORS + 1)/2) { return 1; }
    line(RB_RS_VERIFY_TITLE);
    for (i = 0; i < ITEMS(cases); ++i) {
        mode = cases[i].mode; writes = opens = identities = 0;
        file_sectors = mode == LONG_OUTPUT ? LONG_SECTORS : FILE_SECTORS;
        status = rb_backup_verify_live(&result, mode == LONG_OUTPUT ? &long_claims : &claims,
            file_sectors, &disk, &history, &file);
        if (status != cases[i].status || result.status != status || result.detail != cases[i].detail
            || writes != cases[i].writes || opens != cases[i].opens
            || result.sectors != (status ? 0U : file_sectors) || result.approved_revision != (status ? 0U : 2U)
            || (mode == OTHER_CONFIG && result.error_sector != 41)
            || (mode == OTHER_ORIGINAL && result.error_sector != 5)
            || (mode == OTHER_APPROVAL && result.error_sector != 6)
            || (mode == LATE_READ && result.error_sector != FILE_SECTORS-1)) {
            count("!CASE ", mode); count("STATUS ", status); count("DETAIL ", result.detail);
            count("NESTED ", result.nested); count("WRITTEN ", writes); return 1;
        }
        if (!i) { count(RB_RS_VERIFY_COUNT, result.sectors); }
        if (mode == LAST_DAMAGE) { line(RB_RS_VERIFY_DAMAGE); }
        if (mode == OTHER_APPROVAL) { line(RB_RS_VERIFY_APPROVAL); }
    }
    return 0;
}
