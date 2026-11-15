#include "backup_encode.h"
#include "config.h"
#include "bios_ui.h"
#include "backup_encode_vectors.h"

static rb_u8 metadata[2560];
static struct { rb_u32 before; rb_backup value; rb_u32 after; } source, decoded;
static rb_backup unchanged;
static struct { rb_u32 before; rb_u8 bytes[512]; rb_u32 after; } output;
static rb_u16 size, reads, bad_read, failures, assertions;

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
static rb_u16 zero(const void *p, rb_u16 n)
{
    const rb_u8 *bytes = (const rb_u8 *)p;
    while (n) { if (bytes[--n]) { return 0; } } return 1;
}
static void hex(rb_u16 value)
{
    rb_u16 i;
    static const char digits[] = "0123456789ABCDEF";
    for (i = 4; i; ) { --i; rb_putc(digits[(value >> (i * 4)) & 15]); }
}
static void check(rb_u16 accepted)
{
    ++assertions;
    if (!accepted) { ++failures; rb_putc('!'); hex(assertions); }
}
static void load(void)
{
    rb_backup *b = &source.value;
    rb_backup_extent *e;
    const rb_u8 *p;
    rb_u16 i;
    /* Unused native entries are deliberately dirty; they must not leak into
       the wire table or be touched in the const input. */
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
static rb_u16 __cdecl read_encoded(rb_u32 lba, rb_u8 *out, void *opaque)
{
    rb_u16 i;
    if (opaque != (void *)&source || lba != reads || lba >= size) { bad_read = 1; return 1; }
    ++reads;
    if (lba < 5) { return rb_backup_encode_metadata(&source.value, size, (rb_u16)lba, out); }
    for (i = 0; i < 512; ++i) { out[i] = (rb_u8)(lba * 17 + i); }
    return 0;
}

rb_u16 __cdecl rb_backup_encode_selftest(void)
{
    static const rb_u16 order[] = {4,0,3,1,2,0};
    const rb_u16 *v;
    rb_u16 test, i, j, status, pos, bytes;
    failures = assertions = 0;
    for (test = 0; test < sizeof(encode_vectors) / sizeof(encode_vectors[0]); ++test) {
        v = encode_vectors[test];
        for (i = 0; i < 2560; ++i) { metadata[i] = encode_seeds[v[0]][i]; }
        for (i = v[1]; i < v[1] + v[2]; ++i) { metadata[encode_patches[i][0]] = (rb_u8)encode_patches[i][1]; }
        put32(metadata + 72, rb_crc32(metadata + 512, 2048));
        put32(metadata + 508, rb_crc32(metadata, 508));
        size = v[3] ? v[3] : encode_sizes[v[0]];
        source.before = decoded.before = output.before = 0x12345678UL;
        source.after = decoded.after = output.after = 0x87654321UL;
        load();
        for (j = 0; j < sizeof(order) / sizeof(order[0]); ++j) {
            pos = order[j];
            for (i = 0; i < 512; ++i) { output.bytes[i] = 0xA5; }
            status = rb_backup_encode_metadata(&source.value, size, pos, output.bytes);
            check(status == v[4]);
            check(status ? zero(output.bytes, 512) : equal(output.bytes, metadata + pos * 512, 512));
            check(output.before == 0x12345678UL && output.after == 0x87654321UL
                && equal(&source.value, &unchanged, sizeof(unchanged)));
        }
        if (!v[4]) {
            reads = bad_read = 0;
            for (i = 0; i < sizeof(decoded.value); ++i) { ((rb_u8 *)&decoded.value)[i] = 0xA5; }
            status = rb_backup_validate(&decoded.value, read_encoded, &source, size);
            check(status == v[5] && !bad_read);
            bytes = sizeof(rb_backup) - (RB_BACKUP_MAX - source.value.count) * sizeof(rb_backup_extent);
            check(status ? zero(&decoded.value, sizeof(decoded.value))
                : reads == size && equal(&source.value, &decoded.value, bytes));
        }
        check(source.before == 0x12345678UL && source.after == 0x87654321UL
            && decoded.before == 0x12345678UL && decoded.after == 0x87654321UL
            && equal(&source.value, &unchanged, sizeof(unchanged)));
    }
    /* Invalid API inputs after success must also clear the complete sector. */
    for (i = 0; i < 2560; ++i) { metadata[i] = encode_seeds[0][i]; }
    size = encode_sizes[0]; load();
    for (j = 0; j < 3; ++j) {
        check(!rb_backup_encode_metadata(&source.value, size, 0, output.bytes));
        status = rb_backup_encode_metadata(j ? &source.value : (const rb_backup *)0,
            size, j == 2 ? 0xFFFF : j == 1 ? 5 : 0, output.bytes);
        check(status == RB_BACKUP_FORMAT && zero(output.bytes, 512));
    }
    check(rb_backup_encode_metadata(&source.value, size, 0, (rb_u8 *)0) == RB_BACKUP_FORMAT);
    check(equal(&source.value, &unchanged, sizeof(unchanged))
        && output.before == 0x12345678UL && output.after == 0x87654321UL);
    rb_putc('H'); rb_putc('='); hex(assertions); rb_putc('\r'); rb_putc('\n');
    return failures;
}
