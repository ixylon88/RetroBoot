#include "backup_stream.h"
#include "config.h"
#include "bios_ui.h"
#include "backup_stream_vectors.h"

static rb_u8 metadata[2560], expected[512];
static struct { rb_u32 before; rb_backup value; rb_u32 after; } source;
static rb_backup unchanged;
static struct { rb_u32 before; rb_backup_stream_result value; rb_u32 after; } result;
static const rb_stream_case *current;
static rb_u16 size, reads, sinks, unexpected;

static rb_u16 word(const rb_u8 *p) { return p[0] | ((rb_u16)p[1] << 8); }
static rb_u32 dword(const rb_u8 *p) { return word(p) | ((rb_u32)word(p + 2) << 16); }
static void put32(rb_u8 *p, rb_u32 value)
{
    rb_u16 i;
    for (i = 0; i < 4; ++i) { p[i] = (rb_u8)value; value >>= 8; }
}
static rb_u16 equal(const void *a, const void *b, rb_u16 n)
{
    const rb_u8 *x = (const rb_u8 *)a, *y = (const rb_u8 *)b;
    while (n) { --n; if (x[n] != y[n]) { return 0; } } return 1;
}
static void hex(rb_u16 value)
{
    rb_u16 i;
    static const char digits[] = "0123456789ABCDEF";
    for (i = 4; i; ) { --i; rb_putc(digits[(value >> (i * 4)) & 15]); }
}
static void load(void)
{
    rb_backup *b = &source.value;
    rb_backup_extent *e;
    const rb_u8 *p;
    rb_u16 i;
    for (i = 0; i < sizeof(*b); ++i) { ((rb_u8 *)b)[i] = 0xA5; }
    b->generation = dword(metadata + 16); b->disk_id = dword(metadata + 20);
    b->layout_crc = dword(metadata + 24); b->admin_start = dword(metadata + 28);
    b->admin_sectors = dword(metadata + 32); b->count = word(metadata + 36);
    b->route = word(metadata + 40); b->heads = word(metadata + 42);
    b->sectors_per_track = word(metadata + 44);
    b->capacity_low = dword(metadata + 48); b->capacity_high = dword(metadata + 52);
    for (i = 0; i < 16; ++i) { b->media_id[i] = metadata[56 + i]; }
    for (i = 0; i < b->count && i < RB_BACKUP_MAX; ++i) {
        e = &b->entries[i]; p = metadata + 512 + i * 32;
        e->kind = word(p); e->index = word(p + 2); e->lba = dword(p + 4);
        e->sectors = dword(p + 8); e->file_sector = dword(p + 12);
        e->crc = dword(p + 16); e->owner_start = dword(p + 20);
        e->owner_sectors = dword(p + 24);
    }
    unchanged = *b;
}
static void bytes(rb_u32 pos, rb_u8 *out, rb_u16 changed)
{
    rb_u16 i;
    if (pos < 5) {
        for (i = 0; i < 512; ++i) { out[i] = metadata[(rb_u16)pos * 512 + i]; }
        return;
    }
    for (i = 0; i < 512; ++i) { out[i] = (rb_u8)(pos * 17 + i); }
    if (changed) { out[400] ^= 1; }
    if (current->seed == 4 && pos == 43) { put32(out + 508, rb_crc32(out, 508)); }
}
static rb_u16 __cdecl read_source(rb_u16 kind, rb_u16 index, rb_u32 offset,
    rb_u8 *out, void *opaque)
{
    rb_u16 i;
    rb_u32 pos = 5 + reads % (size - 5);
    const rb_backup_extent *e = (const rb_backup_extent *)0;
    ++reads;
    for (i = 0; i < unchanged.count; ++i) {
        if (pos >= unchanged.entries[i].file_sector
                && pos < unchanged.entries[i].file_sector + unchanged.entries[i].sectors) {
            e = &unchanged.entries[i]; break;
        }
    }
    if (opaque != &source || !e || kind != e->kind || index != e->index
            || offset != pos - e->file_sector || reads > 2 * (size - 5)) {
        ++unexpected; return 1;
    }
    if (current->fault == 1 && reads == current->at) { return 1; }
    bytes(pos, out, current->fault == 4 && reads == current->at);
    if (current->fault == 3 && reads == current->at) { out[400] ^= 1; }
    return 0;
}
static rb_u16 __cdecl consume(rb_u32 pos, const rb_u8 *sector, void *opaque)
{
    /* Check full bytes, not just the same CRC algorithm as the producer.
       Even a failing sink consumes its sector before returning failure. */
    if (opaque != &result || pos != sinks || pos >= size
            || reads != size - 5 + (pos < 5 ? 0 : pos - 4)) { ++unexpected; return 1; }
    bytes(pos, expected, pos >= 5 && current->fault == 4 && reads == current->at);
    if (pos >= 5 && current->fault == 3 && reads == current->at) { expected[400] ^= 1; }
    if (!equal(sector, expected, 512)) { ++unexpected; }
    ++sinks;
    return current->fault == 2 && pos == current->at;
}

#define CHECK(c) do { ++n; if (!(c)) { \
    rb_putc('!'); hex(__LINE__); rb_putc(':'); hex(test); rb_putc(':'); \
    hex(status); rb_putc('/'); hex(reads); rb_putc('/'); hex(sinks); \
    rb_putc('\r'); rb_putc('\n'); return 1; } } while (0)

rb_u16 __cdecl rb_backup_stream_selftest(void)
{
    rb_u16 test, i, n = 0, status;
    rb_backup_stream_result saved;
    for (test = 0; test < sizeof(stream_cases) / sizeof(stream_cases[0]); ++test) {
        current = &stream_cases[test];
        size = current->size ? current->size : stream_sizes[current->seed];
        for (i = 0; i < 2560; ++i) { metadata[i] = stream_seeds[current->seed][i]; }
        for (i = current->patch; i < current->patch + current->patches; ++i) {
            metadata[stream_patches[i][0]] = (rb_u8)stream_patches[i][1];
        }
        put32(metadata + 72, rb_crc32(metadata + 512, 2048));
        put32(metadata + 508, rb_crc32(metadata, 508));
        source.before = result.before = 0x12345678UL;
        source.after = result.after = 0x87654321UL;
        load(); reads = sinks = unexpected = 0; saved = result.value;
        status = rb_backup_stream(current->fault == 8 ? (rb_backup_stream_result *)0 : &result.value,
            current->fault == 5 ? (const rb_backup *)0 : &source.value, size,
            current->fault == 6 ? (rb_backup_source)0 : read_source, &source,
            current->fault == 7 ? (rb_backup_sink)0 : consume, &result);
        CHECK(status == current->status);
        CHECK(current->fault == 8 ? equal(&result.value, &saved, sizeof(saved)) :
            result.value.status == status && result.value.detail == current->detail
            && result.value.kind == current->kind && result.value.index == current->index
            && result.value.file_sector == current->pos);
        CHECK(current->fault == 8 || result.value.sectors == (status ? 0 : size));
        CHECK(reads == current->reads && sinks == current->sinks && !unexpected);
        CHECK(source.before == 0x12345678UL && source.after == 0x87654321UL
            && result.before == 0x12345678UL && result.after == 0x87654321UL
            && equal(&source.value, &unchanged, sizeof(unchanged)));
    }
    rb_putc('J'); rb_putc('='); hex(n); rb_putc('\r'); rb_putc('\n');
    return 0;
}
