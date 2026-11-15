#include "backup_plan.h"
#include "config.h"
#include "bios_ui.h"
#include "backup_plan_vectors.h"

static struct { rb_u32 before; rb_backup_plan result; rb_u32 after; } guarded;
static struct { rb_u32 before; rb_backup_sources result; rb_u32 after; } source_guard;
static rb_backup_target observed;
static rb_rescue_device device;
static const rb_plan_case *current;
static rb_u16 reads, unexpected, trace;

static void hex(rb_u16 value)
{
    rb_u16 i;
    static const char digits[] = "0123456789ABCDEF";
    for (i = 4; i; ) { --i; rb_putc(digits[(value >> (i * 4)) & 15]); }
}
static void trace_hex(rb_u32 value)
{
    rb_u16 i;
    static const char digits[] = "0123456789ABCDEF";
    for (i = 8; i; ) { --i; rb_debug_putc(digits[(value >> (i * 4)) & 15]); }
}
static void fill(void *p, rb_u16 size, rb_u8 value)
{
    rb_u8 *bytes = (rb_u8 *)p;
    while (size) { bytes[--size] = value; }
}
static rb_u16 zeros(const void *p, rb_u16 size)
{
    const rb_u8 *bytes = (const rb_u8 *)p;
    while (size) { if (bytes[--size]) { return 0; } } return 1;
}
static void apply(const rb_plan_patch *patch, rb_u16 count, rb_u32 lba, rb_u8 *out)
{
    rb_u16 i, j;
    rb_u32 value;
    for (i = 0; i < count; ++i) {
        if (patch[i].lba != lba) { continue; }
        value = patch[i].value;
        for (j = 0; j < 4; ++j) { out[patch[i].offset + j] = (rb_u8)value; value >>= 8; }
    }
}
static rb_u16 __cdecl read_mock(rb_u32 lba, rb_u8 *out, void *opaque)
{
    ++reads;
    if (trace) { trace_hex(lba); rb_debug_putc(','); }
    if (opaque != (void *)&device || reads > 2200
            || !(lba == 0 || lba == 63 || (lba >= 126 && lba <= 660)
                || lba == 6257 || lba == 6457 || lba == 6657 || lba == 6857 || lba == 131072)) {
        ++unexpected; return 1;
    }
    if (reads == current->io) { return 1; }
    fill(out, 512, 0); apply(rb_plan_seed, RB_PLAN_SEED_COUNT, lba, out);
    if (reads >= current->start) { apply(current->patches, current->count, lba, out); }
    return 0;
}
static void setup(rb_u16 number)
{
    current = &rb_plan_cases[number]; reads = unexpected = trace = 0;
    fill(&guarded, sizeof(guarded), 0xA5); guarded.before = 0x12345678UL; guarded.after = 0x87654321UL;
    fill(&source_guard, sizeof(source_guard), 0xA5);
    source_guard.before = 0x12345678UL; source_guard.after = 0x87654321UL;
    fill(&device, sizeof(device), 0); device.drive = 0x80; device.mode = 1; device.capacity_low = 262144UL;
    if (current->device == 1 || current->device == 2) { device.heads = 16; device.sectors_per_track = 63; }
    if (current->device == 1) { device.mode = 0; }
    if (current->device == 3) { device.capacity_high = 1; device.capacity_low = 0; }
    if (current->device == 6) { device.drive = 0x81; }
    if (current->device == 7) { device.mode = 2; }
    if (current->device == 8) { device.capacity_low = 0; }
    if (current->device == 9) { device.mode = 0; }
    if (current->device == 10) { device.heads = 16; }
}
static rb_u16 payload(void)
{
    rb_backup_plan *r = &guarded.result;
    rb_capture_extent *e;
    rb_u16 i;
    static const rb_u32 lbas[8] = {0,63,131072,126,6257,6457,6657,6857};
    static const rb_u16 kinds[8] = {0,3,4,4,5,6,7,8};
    static const rb_u8 media[16] = {0xA6,0x21,0x6F,0x34,0x5C,0xD2,0x46,0x77,0x90,0xAB,0xC0,0x13,0x7D,0x84,0x52,0xE9};
    if (r->status) { return zeros((rb_u8 *)r + 12, sizeof(*r) - 12); }
    if (r->count != 8 || r->volumes != 2 || r->live_sectors != (rb_u32)current->reserved + 7
            || r->estimated_container_sectors != r->live_sectors + 6
            || r->observed.status || r->observed.detail || r->observed.error_lba
            || r->observed.disk_id != 0x52425431UL || r->observed.layout_crc != current->layout_crc
            || r->observed.admin_start != 126 || r->observed.admin_sectors != 128457UL
            || r->observed.config_generation != 1 || r->observed.state_generation != 1) { return 0; }
    for (i = 0; i < sizeof(device); ++i) {
        if (((rb_u8 *)&r->device)[i] != ((rb_u8 *)&device)[i]) { return 0; }
    }
    for (i = 0; i < 16; ++i) { if (r->observed.media_id[i] != media[i]) { return 0; } }
    for (i = 0; i < 8; ++i) {
        e = &r->entries[i];
        if (e->kind != kinds[i] || e->index != (i == 3 ? 1 : 0) || e->lba != lbas[i]
                || e->sectors != (i == 2 ? current->reserved : 1)
                || e->owner_start != (i < 2 ? 0 : i == 2 ? 131072UL : 126UL)
                || e->owner_sectors != (i < 2 ? 0 : i == 2 ? current->length : 128457UL)) { return 0; }
    }
    return zeros(r->entries + 8, sizeof(r->entries) - 8 * sizeof(*e));
}
static rb_u16 report(rb_u16 count, rb_u16 failed)
{
    rb_putc(failed ? '!' : 'G'); rb_putc('='); hex(count); rb_putc(13); rb_putc(10); return failed;
}
#define CHECK(c) do { ++n; if (!(c)) { \
    rb_putc('@'); hex(__LINE__); rb_putc(':'); hex(number); rb_putc(':'); \
    hex(guarded.result.status); rb_putc('/'); hex(guarded.result.detail); rb_putc('/'); \
    hex(guarded.result.nested); rb_putc('/'); hex(reads); rb_putc(13); rb_putc(10); \
    return report(n, 1); } } while (0)

rb_u16 __cdecl rb_backup_plan_selftest(void)
{
    rb_u16 number, n = 0;
    rb_backup_plan *r = &guarded.result;
    rb_backup_sources *s = &source_guard.result;
    for (number = 0; number < RB_PLAN_CASES; ++number) {
        setup(number);
        if (!number) { trace = 1; rb_debug_putc('L'); rb_debug_putc('='); }
        rb_backup_plan_capture(r, current->device == 4 ? (const rb_rescue_device *)0 : &device,
            current->device == 5 ? (rb_sector_reader)0 : read_mock, &device);
        if (trace) { rb_debug_putc(13); rb_debug_putc(10); }
        CHECK(r->status == current->status && r->detail == current->detail && r->nested == current->nested);
        CHECK(r->index == current->index && r->error_lba == current->lba);
        CHECK(payload());
        CHECK(reads == current->reads && !unexpected);
        CHECK(guarded.before == 0x12345678UL && guarded.after == 0x87654321UL);
    }
    setup(0); rb_backup_observe_target(&observed, s, &device, read_mock, &device);
    CHECK(!observed.status && reads == RB_PLAN_ACQUISITION * 2 && !unexpected);
    CHECK(s->scan.count == 5 && s->scan.ebr_count == 1 && s->scan.ebr_lba[0] == 63
        && s->scan.entries[0].start == 131072UL && s->scan.entries[4].start == 126);
    CHECK(s->record_lba[0] == 6257 && s->record_lba[1] == 6457 && s->record_lba[2] == 6657 && s->record_lba[3] == 6857);
    /* A failure after prior success must clear the exposed address map. */
    reads = 0; device.drive = 0x81; rb_backup_observe_target(&observed, s, &device, read_mock, &device);
    CHECK(observed.status == RB_BTARGET_PARAMS && observed.detail == 2 && !reads
        && zeros((rb_u8 *)&observed + 8, sizeof(observed) - 8) && zeros(s, sizeof(*s)));
    setup(0); rb_backup_observe_target(&observed, s, (const rb_rescue_device *)0, read_mock, &device);
    CHECK(observed.status == RB_BTARGET_PARAMS && !observed.detail && !reads && zeros(s, sizeof(*s)));
    setup(0); rb_backup_observe_target(&observed, s, &device, (rb_sector_reader)0, &device);
    CHECK(observed.status == RB_BTARGET_PARAMS && !reads && zeros(s, sizeof(*s)));
    CHECK(source_guard.before == 0x12345678UL && source_guard.after == 0x87654321UL);
    setup(0); rb_backup_observe_target(&observed, (rb_backup_sources *)0, &device, read_mock, &device);
    CHECK(!observed.status && reads == RB_PLAN_ACQUISITION * 2 && !unexpected);
    return report(n, 0);
}
