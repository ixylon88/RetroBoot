#include "backup_records.h"
#include "bios_ui.h"
#include "backup_record_vectors.h"

static rb_u8 file[8192];
static struct { rb_u32 before; rb_backup_records value; rb_u32 after; } guarded;
static rb_u16 sectors, calls, io_at, change_at, bad_read;
static rb_u32 requested[32];

static rb_u16 word(const rb_u8 *p) { return p[0] | ((rb_u16)p[1] << 8); }
static rb_u32 dword(const rb_u8 *p) { return word(p) | ((rb_u32)word(p + 2) << 16); }
static void put32(rb_u8 *p, rb_u32 v)
{
    rb_u16 i;
    for (i = 0; i < 4; ++i) { p[i] = (rb_u8)v; v >>= 8; }
}
static rb_u16 __cdecl read_mock(rb_u32 lba, rb_u8 *out, void *opaque)
{
    rb_u16 i;
    if (opaque != (void *)file || lba >= sectors || calls >= 32) { bad_read = 1; return 1; }
    requested[calls++] = lba;
    if (calls == io_at) { return 1; }
    for (i = 0; i < 512; ++i) { out[i] = file[(rb_u16)lba * 512 + i]; }
    if (calls == change_at) { out[0] ^= 1; }
    return 0;
}
static void seal(rb_u16 records)
{
    rb_u16 i, kind, start, length;
    rb_u8 *e;
    for (i = 0; i < word(file + 36); ++i) {
        e = file + 512 + i * 32; kind = word(e);
        start = (rb_u16)dword(e + 12) * 512; length = (rb_u16)dword(e + 8) * 512;
        if (kind >= 5 && kind <= 8 && (records & (1U << (kind - 5)))) {
            put32(file + start + 508, rb_crc32(file + start, 508));
        }
        put32(e + 16, rb_crc32(file + start, length));
    }
    put32(file + 72, rb_crc32(file + 512, 2048));
    put32(file + 508, rb_crc32(file, 508));
}
static void hex(rb_u16 value)
{
    rb_u16 i;
    static const char digits[] = "0123456789ABCDEF";
    for (i = 4; i; ) { --i; rb_debug_putc(digits[(value >> (i * 4)) & 15]); }
}
static rb_u16 clean_failure(void)
{
    const rb_backup_records *r = &guarded.value;
    return !r->partitions && !r->ebrs && !r->boot_areas && !r->config_generation && !r->state_generation
        && r->config_source == RB_CONFIG_NONE && r->state_source == RB_CONFIG_NONE;
}
static rb_u16 correct_reads(rb_u16 source)
{
    rb_u16 i;
    static const rb_u16 after[][7] = {{6,7,10,11,12,13,0}, {6,7,8,12,13,14,15}};
    if (bad_read || calls != sectors + (source ? 7 : 6)) { return 0; }
    for (i = 0; i < sectors; ++i) { if (requested[i] != i) { return 0; } }
    for (i = sectors; i < calls; ++i) { if (requested[i] != after[source][i - sectors]) { return 0; } }
    return 1;
}
static rb_u16 read_diagnostic(void)
{
    rb_u16 i;
    const rb_u8 *e;
    const rb_backup_records *r = &guarded.value;
    if (r->status == RB_BREC_CONTAINER) { return !r->kind && !r->index && !r->error_lba; }
    if (r->status != RB_BREC_IO && r->status != RB_BREC_CHANGED) { return 1; }
    for (i = 0; i < word(file + 36); ++i) {
        e = file + 512 + i * 32;
        if (dword(e + 12) == requested[calls - 1]) {
            return r->kind == word(e) && r->index == word(e + 2) && r->error_lba == dword(e + 4);
        }
    }
    return 0;
}

rb_u16 __cdecl rb_backup_records_selftest(void)
{
    rb_u16 test, i, j, count = 0, failures = 0;
    const rb_u16 *v;
    rb_backup_records *r = &guarded.value;
    for (test = 0; test < sizeof(record_vectors) / sizeof(record_vectors[0]); ++test) {
        v = record_vectors[test]; sectors = record_sizes[v[0]];
        for (i = 0; i < sizeof(file); ++i) { file[i] = i < sectors * 512 ? record_seeds[v[0]][i] : 0; }
        for (j = v[1]; j < v[1] + v[2]; ++j) { file[record_patches[j][0]] = (rb_u8)record_patches[j][1]; }
        if (v[4]) { seal(v[3]); }
        calls = bad_read = 0; io_at = v[5]; change_at = v[6];
        guarded.before = 0x12345678UL; guarded.after = 0x87654321UL;
        for (i = 0; i < sizeof(*r); ++i) { ((rb_u8 *)r)[i] = 0xA5; }
        rb_backup_check_records(r, read_mock, file, sectors);
        ++count;
        if (r->status != v[7] || r->detail != v[8]) {
            ++failures; rb_debug_putc('!'); hex(test); rb_debug_putc(':'); hex(r->status); rb_debug_putc('/'); hex(r->detail);
        }
        ++count;
        if (bad_read || guarded.before != 0x12345678UL || guarded.after != 0x87654321UL) { ++failures; }
        ++count;
        if (r->status ? !clean_failure() : r->partitions != (v[0] ? 6 : 5) || r->ebrs != (v[0] ? 2 : 1)
                || r->boot_areas != (v[0] ? 3 : 2) || r->config_source != v[9] || r->state_source != v[10]
                || r->config_generation != v[11] || r->state_generation != v[12]) { ++failures; }
        ++count;
        if ((r->status ? ((io_at || change_at) && calls != (io_at ? io_at : change_at)) : !correct_reads(v[0]))
                || !read_diagnostic()) { ++failures; }
    }
    rb_debug_putc('C'); rb_debug_putc('='); hex(count); rb_debug_putc('\r'); rb_debug_putc('\n');
    return failures;
}
