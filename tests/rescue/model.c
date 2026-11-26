#include "rescue.h"
#include "bios_ui.h"

rb_u16 rb_format_plan_selftest(void);

static rb_u8 mbr[512], ebr[512];
static rb_u16 reads, fail_at, change_at, count, failures;
static rb_u32 lbas[8];
static rb_rescue_device device;
static rb_rescue_result result;
static void put32(rb_u8 *p, rb_u32 v)
{
    rb_u16 i;
    for (i = 0; i < 4; ++i) { p[i] = (rb_u8)v; v >>= 8; }
}
static rb_u16 __cdecl read_mock(rb_u32 lba, rb_u8 *out, void *opaque)
{
    rb_u16 i;
    const rb_u8 *p = lba ? ebr : mbr;
    (void)opaque;
    if (reads < 8) { lbas[reads] = lba; }
    if (++reads == fail_at || (lba && lba != 63)) { return 1; }
    for (i = 0; i < 512; ++i) { out[i] = p[i]; }
    if (reads == 3 && change_at != 0xFFFF) { out[change_at] ^= 1; }
    return 0;
}
static void setup(void)
{
    rb_u16 i;
    for (i = 0; i < 512; ++i) { mbr[i] = ebr[i] = 0; }
    mbr[432] = 'R'; mbr[433] = 'B'; mbr[434] = 'M'; mbr[435] = '1';
    put32(mbr + 440, 0x52425431UL);
    mbr[498] = 5; put32(mbr + 502, 63); put32(mbr + 506, 4000);
    ebr[450] = 0x16; put32(ebr + 454, 63); put32(ebr + 458, 3000);
    mbr[510] = ebr[510] = 0x55; mbr[511] = ebr[511] = 0xAA;
    device.drive = 0x80; device.mode = 1; device.heads = device.sectors_per_track = 0;
    device.capacity_low = 8192; device.capacity_high = 0;
    reads = fail_at = 0; change_at = 0xFFFF;
}
static void inspect(void) { rb_rescue_inspect(&result, &device, read_mock, (void *)0); }
static rb_u16 empty(void)
{
    return !result.layout && !result.entries && !result.ebrs && !result.signature
        && !result.marker && !result.disk_id && !result.mbr_crc && !result.error_lba;
}
#define CHECK(x) do { ++count; if (!(x)) { ++failures; } } while (0)

rb_u16 __cdecl rb_rescue_selftest(void)
{
    rb_u16 i;
    const rb_u16 changed[] = {0, 432, 440, 444, 446, 510, 511};
    static const char digits[] = "0123456789ABCDEF";
    count = failures = 0;
    setup(); inspect();
    CHECK(!result.status && !result.layout && result.entries == 5 && result.ebrs == 1);
    CHECK(result.disk_id == 0x52425431UL && result.signature == 0xAA55 && result.marker == 1);
    CHECK(result.mbr_crc == 0xAA8A8AB4UL);
    CHECK(reads == 3 && lbas[0] == 0 && lbas[1] == 63 && lbas[2] == 0);
    setup(); mbr[432] = 0; inspect(); CHECK(!result.status && !result.layout && !result.marker);
    setup(); mbr[510] = 0; inspect(); CHECK(!result.status && result.layout == RB_SCAN_SIGNATURE && !result.entries && reads == 2);
    setup(); mbr[498] = 0xEE; inspect(); CHECK(!result.status && result.layout == RB_SCAN_TYPE && !result.entries && reads == 2);
    setup(); ebr[510] = 0; inspect(); CHECK(!result.status && result.layout == RB_SCAN_SIGNATURE && result.error_lba == 63 && !result.entries);
    setup(); ebr[466] = 5; put32(ebr + 470, 0); put32(ebr + 474, 4000); inspect();
    CHECK(!result.status && result.layout == RB_SCAN_LOOP && !result.entries && reads == 3);
    setup(); fail_at = 2; inspect(); CHECK(!result.status && result.layout == RB_SCAN_IO && result.error_lba == 63 && reads == 3);
    for (i = 0; i < sizeof(changed) / sizeof(changed[0]); ++i) {
        setup(); change_at = changed[i]; inspect(); CHECK(result.status == RB_RESCUE_CHANGED && empty());
    }
    setup(); inspect(); reads = 0; fail_at = 1; inspect(); CHECK(result.status == RB_RESCUE_IO && empty() && reads == 1);
    setup(); fail_at = 3; inspect(); CHECK(result.status == RB_RESCUE_IO && empty() && reads == 3);
    setup(); device.drive = 0; inspect(); CHECK(result.status == RB_RESCUE_PARAMS && empty() && !reads);
    setup(); device.mode = 2; inspect(); CHECK(result.status == RB_RESCUE_PARAMS && empty() && !reads);
    setup(); device.capacity_low = 0; inspect(); CHECK(result.status == RB_RESCUE_PARAMS && empty() && !reads);
    setup(); device.mode = 0; inspect(); CHECK(result.status == RB_RESCUE_GEOMETRY && empty() && !reads);
    setup(); device.mode = 0; device.heads = 16; device.sectors_per_track = 63; inspect(); CHECK(!result.status && !result.layout);
    setup(); device.mode = 0; device.heads = 257; device.sectors_per_track = 63; inspect(); CHECK(result.status == RB_RESCUE_GEOMETRY && !reads);
    setup(); device.mode = 0; device.heads = 16; device.sectors_per_track = 64; inspect(); CHECK(result.status == RB_RESCUE_GEOMETRY && !reads);
    setup(); device.capacity_low = 128; inspect(); CHECK(!result.status && result.layout == RB_SCAN_RANGE && !result.entries && reads == 2);
    setup(); device.capacity_low = 0; device.capacity_high = 1; inspect(); CHECK(!result.status && !result.layout);
    CHECK(rb_format_plan_selftest() == 0);
    rb_debug_putc('R'); rb_debug_putc('=');
    for (i = 4; i; ) { --i; rb_debug_putc(digits[(count >> (i * 4)) & 15]); }
    rb_debug_putc('\r'); rb_debug_putc('\n');
    return failures;
}
