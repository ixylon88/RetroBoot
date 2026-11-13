#include "backup.h"
#include "config.h"
#include "bios_ui.h"
#include "backup_vectors.h"

static rb_u8 metadata[2560];
static struct { rb_u32 before; rb_backup result; rb_u32 after; } guarded;
static rb_u16 size, fail_sector, corrupt_sector, reads, bad_read;

static void put32(rb_u8 *p, rb_u32 v)
{
    rb_u16 i;
    for (i = 0; i < 4; ++i) { p[i] = (rb_u8)v; v >>= 8; }
}
static rb_u16 __cdecl read_mock(rb_u32 lba, rb_u8 *out, void *opaque)
{
    rb_u16 i;
    if (opaque != (void *)metadata || lba != reads || lba >= size) { bad_read = 1; return 1; }
    ++reads;
    if (lba == fail_sector) { return 1; }
    for (i = 0; i < 512; ++i) {
        out[i] = lba < 5 ? metadata[(rb_u16)lba * 512 + i] : (rb_u8)(lba * 17 + i);
    }
    if (lba == corrupt_sector) { out[0] ^= 1; }
    return 0;
}
static rb_u16 empty(void)
{
    rb_u16 i;
    const rb_u8 *p = (const rb_u8 *)&guarded.result;
    for (i = 0; i < sizeof(guarded.result); ++i) { if (p[i]) { return 0; } }
    return 1;
}
static void hex(rb_u16 value)
{
    rb_u16 i;
    static const char digits[] = "0123456789ABCDEF";
    for (i = 4; i; ) { --i; rb_debug_putc(digits[(value >> (i * 4)) & 15]); }
}

rb_u16 __cdecl rb_backup_selftest(void)
{
    rb_u16 test, i, j, status, count = 0, failures = 0;
    const rb_u16 *v;
    for (test = 0; test < sizeof(vectors) / sizeof(vectors[0]); ++test) {
        v = vectors[test];
        for (i = 0; i < 2560; ++i) { metadata[i] = seeds[v[0]][i]; }
        for (j = v[1]; j < v[1] + v[2]; ++j) { metadata[patches[j][0]] = (rb_u8)patches[j][1]; }
        if (v[3]) {
            put32(metadata + 72, rb_crc32(metadata + 512, 2048));
            put32(metadata + 508, rb_crc32(metadata, 508));
        }
        size = v[4] ? v[4] : sizes[v[0]]; fail_sector = v[5]; corrupt_sector = v[6];
        reads = bad_read = 0;
        guarded.before = 0x12345678UL; guarded.after = 0x87654321UL;
        /* Successful calls must replace stale results too. */
        for (i = 0; i < sizeof(guarded.result); ++i) { ((rb_u8 *)&guarded.result)[i] = 0xA5; }
        status = rb_backup_validate(&guarded.result, read_mock, metadata, size);
        ++count;
        if (status != v[7]) {
            ++failures; rb_debug_putc('!'); hex(test); rb_debug_putc(':'); hex(status);
        }
        ++count;
        if (bad_read || guarded.before != 0x12345678UL || guarded.after != 0x87654321UL) { ++failures; }
        ++count;
        if (status ? !empty() : reads != size || guarded.result.disk_id != 0x52425431UL
                || guarded.result.count != (v[0] == 3 ? 42 : 8)
                || guarded.result.entries[guarded.result.count - 1].kind != RB_BACKUP_STATE_B) { ++failures; }
    }
    rb_debug_putc('B'); rb_debug_putc('='); hex(count); rb_debug_putc('\r'); rb_debug_putc('\n');
    return failures;
}
