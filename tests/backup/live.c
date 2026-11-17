#include "backup_live.h"
#include "config.h"
#include "bios_ui.h"
#include "backup_live_vectors.h"

static rb_u8 metadata[2560], expected[512];
static struct { rb_u32 before; rb_backup value; rb_u32 after; } input;
static rb_backup unchanged;
static rb_rescue_device device, unchanged_device;
static struct { rb_u32 before; rb_backup_live_result value; rb_u32 after; } result;
static const rb_live_case *current;
static const rb_live_seed *seed;
static rb_u16 reads, mbrs, sinks, unexpected, trace;

static rb_u16 word(const rb_u8 *p) { return p[0] | ((rb_u16)p[1] << 8); }
static rb_u32 dword(const rb_u8 *p) { return word(p) | ((rb_u32)word(p + 2) << 16); }
static void put32(rb_u8 *p, rb_u32 value)
{
    rb_u16 i;
    for (i = 0; i < 4; ++i) { p[i] = (rb_u8)value; value >>= 8; }
}
static void fill(void *p, rb_u16 size, rb_u8 value)
{
    rb_u8 *bytes = (rb_u8 *)p;
    while (size) { bytes[--size] = value; }
}
static rb_u16 equal(const void *a, const void *b, rb_u16 size)
{
    const rb_u8 *x = (const rb_u8 *)a, *y = (const rb_u8 *)b;
    while (size) { --size; if (x[size] != y[size]) { return 0; } }
    return 1;
}
static void hex(rb_u32 value, rb_u16 digits, rb_u16 debug)
{
    static const char alphabet[] = "0123456789ABCDEF";
    char c;
    while (digits) {
        --digits; c = alphabet[(rb_u16)(value >> (digits * 4)) & 15];
        if (debug) { rb_debug_putc(c); } else { rb_putc(c); }
    }
}
static void apply(const rb_live_patch *patch, rb_u16 count, rb_u32 lba, rb_u8 *out)
{
    rb_u16 i;
    for (i = 0; i < count; ++i) {
        if (patch[i].lba == lba) { put32(out + patch[i].offset, patch[i].value); }
    }
}
static void disk_bytes(rb_u32 lba, rb_u8 *out)
{
    fill(out, 512, 0);
    apply(live_disk_base, RB_LIVE_DISK_BASE, lba, out);
    apply(seed->disk, seed->disk_count, lba, out);
    apply(live_disk_edits + current->disk_edit, current->disk_edits, lba, out);
}
static void mutation(rb_u32 lba, rb_u8 *out)
{
    if ((current->fault == 4 || current->fault == 5) && reads == current->at) {
        out[400] ^= 1;
        if (current->fault == 5) { put32(out + 508, rb_crc32(out, 508)); }
    }
    if (current->fault == 6 && reads >= current->at && (lba == 6257 || lba == 6457)) {
        put32(out + 16, 2); put32(out + 508, rb_crc32(out, 508));
    }
}
static rb_u16 __cdecl read_disk(rb_u32 lba, rb_u8 *out, void *opaque)
{
    ++reads;
    if (trace) { hex(lba, 8, 1); rb_debug_putc(','); }
    if (opaque != &device || reads > current->reads
            || !(lba == 0 || lba == 63 || (lba >= 126 && lba <= 660)
                || lba == 6257 || lba == 6457 || lba == 6657 || lba == 6857
                || (lba >= 131072UL && lba < 133107UL))) {
        ++unexpected; return 1;
    }
    if (current->fault == 1 && reads == current->at) { return 1; }
    disk_bytes(lba, out); mutation(lba, out); return 0;
}
static void explicit_bytes(rb_u16 kind, rb_u8 *out)
{
    rb_u16 i;
    for (i = 0; i < 512; ++i) { out[i] = (rb_u8)((kind == 1 ? 0x51 : 0xA2) + (kind == 1 ? 3 : 5)*i); }
}
static rb_u16 __cdecl read_mbr(rb_u16 kind, rb_u16 index, rb_u32 offset, rb_u8 *out, void *opaque)
{
    ++mbrs;
    if (opaque != &input || index || offset || kind != 1 + ((mbrs - 1) & 1) || mbrs > 4) {
        ++unexpected; return 1;
    }
    if (current->fault == 2 && mbrs == current->at) { return 1; }
    explicit_bytes(kind, out); return 0;
}
static rb_u16 __cdecl consume(rb_u32 pos, const rb_u8 *sector, void *opaque)
{
    rb_u16 i, found = 0;
    rb_u32 lba;
    const rb_backup_extent *e;
    if (opaque != &result || pos != sinks || pos >= seed->sectors) { ++unexpected; return 1; }
    if (pos < 5) {
        for (i = 0; i < 512; ++i) { expected[i] = metadata[(rb_u16)pos*512 + i]; }
    } else {
        for (i = 0; i < unchanged.count; ++i) {
            e = &unchanged.entries[i];
            if (pos < e->file_sector || pos >= e->file_sector + e->sectors) { continue; }
            if (e->kind <= 2) { explicit_bytes(e->kind, expected); }
            else { lba = e->lba + pos - e->file_sector; disk_bytes(lba, expected); mutation(lba, expected); }
            found = 1; break;
        }
        if (!found) { ++unexpected; return 1; }
    }
    if (!equal(sector, expected, 512)) { ++unexpected; }
    ++sinks;
    return current->fault == 3 && pos == current->at;
}
static void setup(rb_u16 number)
{
    const rb_live_patch *patch;
    const rb_u8 *p;
    rb_backup *b = &input.value;
    rb_backup_extent *e;
    rb_u16 i;
    current = &live_cases[number]; seed = &live_seeds[current->seed];
    reads = mbrs = sinks = unexpected = trace = 0;
    fill(metadata, sizeof(metadata), 0);
    for (i = 0; i < seed->metadata_count; ++i) {
        patch = &seed->metadata[i]; put32(metadata + (rb_u16)patch->lba*512 + patch->offset, patch->value);
    }
    apply(live_edits + current->edit, current->edits, 0, metadata);
    fill(b, sizeof(*b), 0xA5);
    b->generation = dword(metadata + 16); b->disk_id = dword(metadata + 20);
    b->layout_crc = dword(metadata + 24); b->admin_start = dword(metadata + 28);
    b->admin_sectors = dword(metadata + 32); b->count = word(metadata + 36);
    b->route = word(metadata + 40); b->heads = word(metadata + 42);
    b->sectors_per_track = word(metadata + 44);
    b->capacity_low = dword(metadata + 48); b->capacity_high = dword(metadata + 52);
    for (i = 0; i < 16; ++i) { b->media_id[i] = metadata[56 + i]; }
    for (i = 0; i < b->count && i < RB_BACKUP_MAX; ++i) {
        e = &b->entries[i]; p = metadata + 512 + i*32;
        e->kind = word(p); e->index = word(p + 2); e->lba = dword(p + 4);
        e->sectors = dword(p + 8); e->file_sector = dword(p + 12);
        e->crc = dword(p + 16); e->owner_start = dword(p + 20); e->owner_sectors = dword(p + 24);
    }
    unchanged = *b; device = unchanged_device = seed->device;
    input.before = result.before = 0x12345678UL;
    input.after = result.after = 0x87654321UL;
}

#define CHECK(c) do { ++n; if (!(c)) { \
    rb_putc('!'); hex(__LINE__,4,0); rb_putc(':'); hex(number,4,0); rb_putc(':'); \
    hex(status,4,0); rb_putc('/'); hex(r->detail,4,0); rb_putc('/'); \
    hex(reads,4,0); rb_putc('/'); hex(mbrs,4,0); rb_putc('/'); hex(sinks,4,0); \
    rb_putc('/'); hex(unexpected,4,0); rb_putc(13); rb_putc(10); return 1; } } while (0)

rb_u16 __cdecl rb_backup_live_selftest(void)
{
    rb_u16 number, n = 0, status;
    rb_backup_live_result saved;
    rb_backup_live_result *r = &result.value;
    fill(r, sizeof(*r), 0xA5);
    for (number = 0; number < RB_LIVE_CASES; ++number) {
        setup(number); saved = *r;
        if (!number) { trace = 1; rb_debug_putc('L'); rb_debug_putc('='); }
        status = rb_backup_live_stream(current->fault == 10 ? (rb_backup_live_result *)0 : r,
            current->fault == 11 ? (const rb_backup *)0 : &input.value,
            current->size ? current->size : seed->sectors,
            current->fault == 12 ? (const rb_rescue_device *)0 : &device,
            current->fault == 13 ? (rb_sector_reader)0 : read_disk, &device,
            current->fault == 14 ? (rb_backup_source)0 : read_mbr, &input,
            current->fault == 15 ? (rb_backup_sink)0 : consume, &result);
        if (trace) { rb_debug_putc(13); rb_debug_putc(10); }
        CHECK(status == current->status && (current->fault == 10 || r->status == status));
        CHECK(current->fault == 10 ? equal(r, &saved, sizeof(saved)) :
            r->detail == current->detail && r->error_lba == current->lba
            && r->capture_status == current->capture_status && r->capture_detail == current->capture_detail
            && r->capture_nested == current->capture_nested && r->capture_index == current->capture_index
            && r->stream.status == current->stream && !r->stream.detail
            && r->stream.kind == current->kind && r->stream.index == current->index && r->stream.file_sector == current->pos);
        CHECK(current->fault == 10 || r->stream.sectors == (status ? 0 : seed->sectors));
        CHECK(reads == current->reads && mbrs == current->mbrs && sinks == current->sinks && !unexpected);
        CHECK(input.before == 0x12345678UL && input.after == 0x87654321UL
            && result.before == 0x12345678UL && result.after == 0x87654321UL
            && equal(&input.value, &unchanged, sizeof(unchanged)) && equal(&device, &unchanged_device, sizeof(device)));
    }
    rb_putc('K'); rb_putc('='); hex(n,4,0); rb_putc(13); rb_putc(10); return 0;
}
