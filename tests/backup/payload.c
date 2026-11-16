#include "backup_payload.h"
#include "bios_ui.h"
#include "backup_payload_vectors.h"

static struct { rb_u32 before; rb_backup_payloads result; rb_u32 after; } guarded;
static rb_rescue_device device, original_device;
static const rb_plan_case *current;
static rb_u16 reads, unexpected, trace, stop;

static void hex(rb_u32 value, rb_u16 digits, rb_u16 debug)
{
    static const char alphabet[] = "0123456789ABCDEF";
    char c;
    while (digits) {
        --digits; c = alphabet[(rb_u16)(value >> (digits * 4)) & 15];
        if (debug) { rb_debug_putc(c); } else { rb_putc(c); }
    }
}
static void fill(void *p, rb_u16 size, rb_u8 value)
{
    rb_u8 *bytes = (rb_u8 *)p;
    while (size) { bytes[--size] = value; }
}
static rb_u16 equal(const void *a, const void *b, rb_u16 size)
{
    const rb_u8 *x = (const rb_u8 *)a, *y = (const rb_u8 *)b;
    while (size) { --size; if (x[size] != y[size]) { return 0; } } return 1;
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
    if (trace) { hex(lba, 8, 1); rb_debug_putc(','); }
    if (opaque != (void *)&device || reads > 10300
            || !(lba == 0 || lba == 63 || (lba >= 126 && lba <= 660)
                || lba == 6257 || lba == 6457 || lba == 6657 || lba == 6857
                || (lba >= 131072UL && lba < 133107UL))) {
        ++unexpected; return 1;
    }
    if (reads == current->io) { return 1; }
    fill(out, 512, 0); apply(rb_plan_seed, RB_PLAN_SEED_COUNT, lba, out);
    apply(current->initial, current->initial_count, lba, out);
    if (reads >= current->start && (!stop || reads < stop)) {
        apply(current->patches, current->count, lba, out);
    }
    return 0;
}
static void setup(rb_u16 number)
{
    current = &rb_plan_cases[number]; stop = rb_payload_stop[number];
    reads = unexpected = trace = 0;
    fill(&guarded, sizeof(guarded), 0xA5);
    guarded.before = 0x12345678UL; guarded.after = 0x87654321UL;
    fill(&device, sizeof(device), 0); device.drive = 0x80; device.mode = 1; device.capacity_low = 262144UL;
    if (current->device == 1 || current->device == 2) { device.heads = 16; device.sectors_per_track = 63; }
    if (current->device == 1) { device.mode = 0; }
    if (current->device == 3) { device.capacity_high = 1; device.capacity_low = 0; }
    if (current->device == 6) { device.drive = 0x81; }
    if (current->device == 7) { device.mode = 2; }
    if (current->device == 8) { device.capacity_low = 0; }
    if (current->device == 9) { device.mode = 0; }
    if (current->device == 10) { device.heads = 16; }
    original_device = device;
}
static rb_u16 claims(rb_u16 number)
{
    rb_backup_plan *r = &guarded.result.plan;
    rb_capture_extent *e;
    rb_u16 i;
    static const rb_u32 lbas[8] = {0,63,131072,126,6257,6457,6657,6857};
    static const rb_u16 kinds[8] = {0,3,4,4,5,6,7,8};
    if (r->status) { return zeros((rb_u8 *)&guarded.result + 12, sizeof(guarded.result) - 12); }
    if (r->count != 8 || r->volumes != 2 || r->live_sectors != (rb_u32)current->reserved + 7
            || r->estimated_container_sectors != r->live_sectors + 6
            || r->observed.status || r->observed.detail || r->observed.error_lba
            || r->observed.disk_id != 0x52425431UL || r->observed.layout_crc != current->layout_crc
            || r->observed.admin_start != 126 || r->observed.admin_sectors != 128457UL
            || r->observed.config_generation != current->config_generation
            || r->observed.state_generation != current->state_generation
            || !equal(&r->device, &device, sizeof(device))) { return 0; }
    for (i = 0; i < 8; ++i) {
        e = &r->entries[i];
        if (e->kind != kinds[i] || e->index != (i == 3 ? 1 : 0) || e->lba != lbas[i]
                || e->sectors != (i == 2 ? current->reserved : 1)
                || e->owner_start != (i < 2 ? 0 : i == 2 ? 131072UL : 126UL)
                || e->owner_sectors != (i < 2 ? 0 : i == 2 ? current->length : 128457UL)
                || guarded.result.crc[i] != rb_payload_crc[number][i]) { return 0; }
    }
    return zeros(r->entries + 8, sizeof(r->entries) - 8 * sizeof(*e))
        && zeros(guarded.result.crc + 8, sizeof(guarded.result.crc) - 8 * sizeof(rb_u32));
}
static rb_u16 report(rb_u16 count, rb_u16 failed)
{
    rb_putc(failed ? '!' : 'I'); rb_putc('='); hex(count, 4, 0);
    rb_putc(13); rb_putc(10); return failed;
}
#define CHECK(c) do { ++n; if (!(c)) { \
    rb_putc('@'); hex(__LINE__, 4, 0); rb_putc(':'); hex(number, 4, 0); \
    rb_putc(':'); hex(r->status, 4, 0); rb_putc('/'); hex(reads, 4, 0); \
    rb_putc(13); rb_putc(10); return report(n, 1); } } while (0)

rb_u16 __cdecl rb_backup_payload_selftest(void)
{
    rb_u16 number, n = 0;
    rb_backup_plan *r = &guarded.result.plan;
    for (number = 0; number < RB_PLAN_CASES; ++number) {
        setup(number);
        if (!number) { trace = 1; rb_debug_putc('P'); rb_debug_putc('='); }
        rb_backup_payload_capture(&guarded.result, current->device == 4 ? (const rb_rescue_device *)0 : &device,
            current->device == 5 ? (rb_sector_reader)0 : read_mock, &device);
        if (trace) { rb_debug_putc(13); rb_debug_putc(10); }
        CHECK(r->status == current->status && r->detail == current->detail && r->nested == current->nested);
        CHECK(r->index == current->index && r->error_lba == current->lba);
        CHECK(claims(number));
        CHECK(reads == current->reads && !unexpected);
        CHECK(guarded.before == 0x12345678UL && guarded.after == 0x87654321UL
            && equal(&device, &original_device, sizeof(device)));
    }
    setup(0); rb_backup_payload_capture(&guarded.result, &device, read_mock, &device);
    CHECK(!r->status && claims(0));
    /* Reuse the successful result without poisoning it; a late second-pass
       I/O failure must revoke every previously returned extent and checksum. */
    reads = trace = 0; number = RB_PAYLOAD_FAILURE_CASE; current = &rb_plan_cases[number];
    rb_backup_payload_capture(&guarded.result, &device, read_mock, &device);
    CHECK(r->status == current->status && r->detail == current->detail
        && !r->nested && r->index == current->index && r->error_lba == current->lba);
    CHECK(claims(number) && reads == current->reads && !unexpected);
    CHECK(guarded.before == 0x12345678UL && guarded.after == 0x87654321UL);
    return report(n, 0);
}
