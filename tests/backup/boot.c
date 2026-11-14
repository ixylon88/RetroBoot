#include "backup_boot.h"
#include "bios_ui.h"
#include "backup_boot_vectors.h"

static rb_u8 metadata[2560], scratch[512];
static rb_u16 source, first_patch, patch_count, calls, io_at, change_at, bad_read;
static rb_u16 requested[512];
static struct { rb_u32 before; rb_backup_boot value; rb_u32 after; } guarded;

static rb_u16 word(const rb_u8 *p) { return p[0] | ((rb_u16)p[1] << 8); }
static rb_u32 dword(const rb_u8 *p) { return word(p) | ((rb_u32)word(p + 2) << 16); }
static void put32(rb_u8 *p, rb_u32 v)
{
    rb_u16 i;
    for (i = 0; i < 4; ++i) { p[i] = (rb_u8)v; v >>= 8; }
}
static rb_u32 crc_update(rb_u32 crc, const rb_u8 *p)
{
    rb_u16 i, bit;
    for (i = 0; i < 512; ++i) {
        crc ^= p[i];
        for (bit = 0; bit < 8; ++bit) { crc = (crc >> 1) ^ ((crc & 1) ? 0xEDB88320UL : 0); }
    }
    return crc;
}
static void raw(rb_u16 lba, rb_u8 *out)
{
    rb_u16 i, j, pool;
    const rb_u16 *span, *patch;
    for (i = 0; i < 512; ++i) { out[i] = 0; }
    pool = seed_maps[seed_sources[source][0] + lba];
    for (i = seed_pools[pool][0]; i < seed_pools[pool][0] + seed_pools[pool][1]; ++i) {
        span = seed_spans[i];
        for (j = 0; j < span[2]; ++j) { out[span[0] + j] = seed_bytes[span[1] + j]; }
    }
    for (i = first_patch; i < first_patch + patch_count; ++i) {
        patch = boot_patches[i];
        if (patch[0] == lba) { out[patch[1]] = (rb_u8)patch[2]; }
    }
    /* All semantic mutations deliberately retain valid inner record CRCs. */
    for (i = 0; i < word(metadata + 36); ++i) {
        const rb_u8 *e = metadata + 512 + i * 32;
        if (word(e) >= 5 && word(e) <= 8 && dword(e + 12) == lba) {
            put32(out + 508, rb_crc32(out, 508));
        }
    }
}
static void prepare(void)
{
    rb_u16 i, j;
    rb_u8 *e;
    rb_u32 crc;
    /* The raw reader's record loop must not see previous metadata. */
    for (i = 0; i < sizeof(metadata); ++i) { metadata[i] = 0; }
    for (i = 0; i < 5; ++i) { raw(i, metadata + i * 512); }
    for (i = 0; i < word(metadata + 36); ++i) {
        e = metadata + 512 + i * 32; crc = 0xFFFFFFFFUL;
        for (j = 0; j < (rb_u16)dword(e + 8); ++j) {
            raw((rb_u16)dword(e + 12) + j, scratch); crc = crc_update(crc, scratch);
        }
        put32(e + 16, crc ^ 0xFFFFFFFFUL);
    }
    put32(metadata + 72, rb_crc32(metadata + 512, 2048));
    put32(metadata + 508, rb_crc32(metadata, 508));
}
static rb_u16 __cdecl read_mock(rb_u32 lba, rb_u8 *out, void *opaque)
{
    rb_u16 i;
    if (opaque != (void *)metadata || lba >= seed_sources[source][1] || calls >= 512) { bad_read = 1; return 1; }
    requested[calls++] = (rb_u16)lba;
    if (calls == io_at) { return 1; }
    if (lba < 5) {
        for (i = 0; i < 512; ++i) { out[i] = metadata[(rb_u16)lba * 512 + i]; }
    } else { raw((rb_u16)lba, out); }
    if (calls == change_at) { out[100] ^= 1; }
    return 0;
}
static void hex(rb_u16 value)
{
    rb_u16 i;
    static const char digits[] = "0123456789ABCDEF";
    for (i = 4; i; ) { --i; rb_debug_putc(digits[(value >> (i * 4)) & 15]); }
}
static rb_u16 correct_reads(void)
{
    rb_u16 i, j, n = seed_sources[source][1], at = 0;
    rb_u32 cursor;
    const rb_u8 *e;
    for (i = 0; i < n; ++i) { if (requested[at++] != i) { return 0; } }
    /* Approved MBR, EBR, configuration A/B, state A/B. */
    for (i = 0; i < word(metadata + 36); ++i) {
        e = metadata + 512 + i * 32;
        if (word(e) == 2 || word(e) == 3 || word(e) >= 5) {
            if (requested[at++] != dword(e + 12)) { return 0; }
        }
    }
    /* Primary target precedes the logical admin volume in scanner order. */
    cursor = 131072;
    for (;;) {
        for (i = 0; i < word(metadata + 36); ++i) {
            e = metadata + 512 + i * 32;
            if (word(e) == 4 && dword(e + 4) == cursor) { break; }
        }
        if (i == word(metadata + 36)) { break; }
        for (j = 0; j < (rb_u16)dword(e + 8); ++j) {
            if (requested[at++] != dword(e + 12) + j) { return 0; }
        }
        cursor += dword(e + 8);
    }
    for (i = 0; i < word(metadata + 36); ++i) {
        e = metadata + 512 + i * 32;
        if (word(e) == 4 && dword(e + 4) == 126 && requested[at++] != dword(e + 12)) { return 0; }
    }
    return at == calls;
}
static rb_u16 diagnostic(void)
{
    rb_u16 i;
    rb_u32 lba;
    const rb_u8 *e;
    const rb_backup_boot *r = &guarded.value;
    if (!r->status) { return !r->detail && !r->record_detail && !r->kind && !r->index && !r->error_lba; }
    if (r->status == RB_BBOOT_RECORDS) { return r->kind == 2 && !r->index && !r->error_lba && !r->record_detail; }
    if (r->kind != 4 || r->record_detail) { return 0; }
    if (r->status == RB_BBOOT_COVERAGE && r->detail == 1) {
        return r->index == RB_CONFIG_NONE && r->error_lba == (source == 2 ? 131075UL : 131104UL);
    }
    for (i = 0; i < word(metadata + 36); ++i) {
        e = metadata + 512 + i * 32;
        if (word(e) != 4 || word(e + 2) != r->index) { continue; }
        lba = dword(e + 4);
        if (r->error_lba < lba || r->error_lba - lba >= dword(e + 8)) { return 0; }
        if (r->status == RB_BBOOT_IO) {
            return requested[calls - 1] == dword(e + 12) + r->error_lba - lba;
        }
        if (r->status == RB_BBOOT_CHANGED) { return r->error_lba == lba; }
        return 1;
    }
    return 0;
}

rb_u16 __cdecl rb_backup_boot_selftest(void)
{
    rb_u16 test, i, failures = 0, count = 0;
    rb_backup_boot *r = &guarded.value;
    const rb_u16 *v;
    for (test = 0; test < sizeof(boot_vectors) / sizeof(boot_vectors[0]); ++test) {
        v = boot_vectors[test]; source = v[0]; first_patch = v[1]; patch_count = v[2];
        prepare(); calls = bad_read = 0; io_at = v[3]; change_at = v[4];
        guarded.before = 0x12345678UL; guarded.after = 0x87654321UL;
        for (i = 0; i < sizeof(*r); ++i) { ((rb_u8 *)r)[i] = 0xA5; }
        rb_backup_check_boot(r, read_mock, metadata, seed_sources[source][1]);
        ++count;
        if (r->status != v[5] || r->detail != v[6]) {
            ++failures; rb_debug_putc('!'); hex(test); rb_debug_putc(':'); hex(r->status); rb_debug_putc('/'); hex(r->detail);
        }
        ++count;
        if (bad_read || guarded.before != 0x12345678UL || guarded.after != 0x87654321UL) { ++failures; }
        ++count;
        if (r->status ? (r->volumes || r->fat16 || r->fat32 || r->reserved_sectors || r->ready_matches)
                : (r->volumes != 2 || r->fat16 != (source == 1 || source == 6 ? 2 : 1)
                   || r->fat32 != (source == 1 || source == 6 ? 0 : 1)
                   || r->reserved_sectors != v[7] + 1 || r->ready_matches != v[8])) { ++failures; }
        ++count;
        if ((io_at && calls != io_at) || (!r->status && !correct_reads())) { ++failures; }
        ++count;
        if (!diagnostic() || r->kind != v[9] || r->index != v[10]
                || r->error_lba != ((rb_u32)v[11] | ((rb_u32)v[12] << 16))) { ++failures; }
    }
    rb_debug_putc('D'); rb_debug_putc('='); hex(count); rb_debug_putc('\r'); rb_debug_putc('\n');
    return failures;
}
