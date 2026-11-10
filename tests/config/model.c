#include "config.h"
#include "config_fixture.h"

static void put32(rb_u8 *p, rb_u32 n)
{
    rb_u16 i;
    for (i = 0; i < 4; ++i) { p[i] = (rb_u8)n; n >>= 8; }
}

static void seal(rb_u8 *p) { put32(p + 508, rb_crc32(p, 508)); }

static void setup(rb_partition_scan *s, rb_u8 *a, rb_u8 *b)
{
    rb_u16 i;
    rb_u8 *bytes = (rb_u8 *)s;
    for (i = 0; i < sizeof(*s); ++i) { bytes[i] = 0; }
    s->disk_id = 0x52425431UL; s->count = 5; s->ebr_count = 1; s->ebr_lba[0] = 63;
    for (i = 0; i < 4; ++i) { s->entries[i].slot = i + 1; }
    s->entries[0].type = 6; s->entries[0].flag = 0x80;
    s->entries[0].start = 131072UL; s->entries[0].sectors = 5073;
    s->entries[3].type = 5; s->entries[3].start = 63; s->entries[3].sectors = 128520UL;
    s->entries[4].type = 0x16; s->entries[4].start = 126; s->entries[4].sectors = 128457UL;
    s->entries[4].slot = 1; s->entries[4].logical = 1; s->entries[4].table_lba = 63;
    for (i = 0; i < 512; ++i) { a[i] = b[i] = rb_config_vector[i]; }
}

static rb_u16 cleared(const rb_config *r)
{
    rb_u16 i;
    const rb_u8 *bytes = (const rb_u8 *)r;
    for (i = 0; i < sizeof(*r); ++i) { if (bytes[i] != 0) { return 0; } }
    return 1;
}

static rb_u16 report(rb_u16 n)
{
    const char digits[] = "0123456789ABCDEF";
    rb_putc('K'); rb_putc('=');
    rb_putc(digits[(n >> 12) & 15]); rb_putc(digits[(n >> 8) & 15]);
    rb_putc(digits[(n >> 4) & 15]); rb_putc(digits[n & 15]); rb_putc(13); rb_putc(10);
    return n;
}

#define CHECK(c) do { ++n; if (!(c)) { return report(n); } } while (0)
#define RESET() setup(&scan, a, b)
#define DECODE() rb_config_decode(&r.config, a, 512, &scan, &scan.entries[4])
#define REJECT(code) do { seal(a); CHECK(DECODE() == (code) && cleared(&r.config)); } while (0)
#define SELECT(mask) rb_config_select(&r, a, b, mask, &scan, &scan.entries[4])

rb_u16 __cdecl rb_config_selftest(void)
{
    rb_partition_scan scan;
    rb_config_result r;
    rb_u8 a[512], b[512];
    rb_u16 n = 0, i;
    rb_u32 crc;
    const rb_u8 vector[] = "123456789";
    const rb_u16 format_offsets[] = {0, 5, 8, 10, 12, 37, 39, 45, 63, 448, 507};
    const rb_u16 profile_offsets[] = {76, 77, 78, 79, 80, 81, 82, 83, 108, 111};
    CHECK(rb_crc32(vector, 9) == 0xCBF43926UL);
    CHECK(rb_crc32(vector, 0) == 0);
    RESET(); CHECK(DECODE() == 0 && r.config.count == 1 && r.config.generation == 100
        && r.config.default_id == 0x12345678UL && r.config.language == 1 && r.config.countdown == 10);
    CHECK((rb_u8)r.config.entries[0].name[0] == 0x8E && (rb_u8)r.config.entries[0].name[6] == 0xE1
          && r.config.entries[0].name[12] == 0 && r.config.entries[0].approved == 1);
    crc = rb_layout_crc(&scan); scan.entries[0].type = 0x16; scan.entries[0].flag = 0;
    CHECK(rb_layout_crc(&scan) == crc && DECODE() == 0);
    ++scan.entries[0].start; CHECK(rb_layout_crc(&scan) != crc); REJECT(RB_CONFIG_IDENTITY);
    RESET(); ++scan.ebr_lba[0]; REJECT(RB_CONFIG_IDENTITY);
    RESET(); ++scan.entries[4].table_lba; REJECT(RB_CONFIG_IDENTITY);
    RESET(); ++scan.disk_id; REJECT(RB_CONFIG_IDENTITY);
    RESET(); scan.status = RB_SCAN_IO; REJECT(RB_CONFIG_IDENTITY);
    RESET(); scan.count = 21; REJECT(RB_CONFIG_IDENTITY);
    RESET(); scan.ebr_count = 17; REJECT(RB_CONFIG_IDENTITY);
    RESET(); scan.entries[4].logical = 0; REJECT(RB_CONFIG_IDENTITY);
    RESET(); scan.entries[4].type = 6; REJECT(RB_CONFIG_IDENTITY);
    RESET(); a[20] ^= 1; REJECT(RB_CONFIG_IDENTITY);
    RESET(); a[24] ^= 1; REJECT(RB_CONFIG_IDENTITY);
    RESET(); a[28] ^= 1; REJECT(RB_CONFIG_IDENTITY);
    RESET(); a[32] ^= 1; REJECT(RB_CONFIG_IDENTITY);
    RESET(); CHECK(rb_config_decode(&r.config, a, 0, &scan, &scan.entries[4]) == RB_CONFIG_FORMAT && cleared(&r.config));
    CHECK(rb_config_decode(&r.config, a, 511, &scan, &scan.entries[4]) == RB_CONFIG_FORMAT);
    CHECK(rb_config_decode(&r.config, a, 513, &scan, &scan.entries[4]) == RB_CONFIG_FORMAT);
    for (i = 0; i < sizeof(format_offsets) / sizeof(format_offsets[0]); ++i) {
        RESET(); a[format_offsets[i]] ^= 0x80; REJECT(RB_CONFIG_FORMAT);
    }
    RESET(); put32(a + 16, 0); REJECT(RB_CONFIG_FORMAT);
    RESET(); a[36] = 9; REJECT(RB_CONFIG_FORMAT);
    RESET(); a[38] = 61; REJECT(RB_CONFIG_FORMAT);
    RESET(); a[44] = 2; REJECT(RB_CONFIG_FORMAT);
    RESET(); a[112] = 1; REJECT(RB_CONFIG_FORMAT);
    RESET(); a[508] ^= 1; CHECK(DECODE() == RB_CONFIG_CRC && cleared(&r.config));
    for (i = 0; i < sizeof(profile_offsets) / sizeof(profile_offsets[0]); ++i) {
        RESET(); a[profile_offsets[i]] = 0xFF; REJECT(RB_CONFIG_PROFILE);
    }
    RESET(); put32(a + 64, 0); REJECT(RB_CONFIG_PROFILE);
    RESET(); a[68] ^= 1; REJECT(RB_CONFIG_PROFILE);
    RESET(); a[72] ^= 1; REJECT(RB_CONFIG_PROFILE);
    RESET(); a[76] = 0; REJECT(RB_CONFIG_PROFILE);
    RESET(); a[76] = 2; REJECT(RB_CONFIG_PROFILE);
    RESET(); a[79] = 1; REJECT(RB_CONFIG_PROFILE);
    RESET(); a[81] = 0; REJECT(RB_CONFIG_PROFILE);
    RESET(); a[81] = 9; REJECT(RB_CONFIG_PROFILE);
    RESET(); a[84] = 31; REJECT(RB_CONFIG_PROFILE);
    RESET(); a[84] = 127; REJECT(RB_CONFIG_PROFILE);
    RESET(); a[107] = 32; REJECT(RB_CONFIG_PROFILE);
    RESET(); a[40] ^= 1; REJECT(RB_CONFIG_PROFILE);
    RESET(); a[36] = 2; for (i = 0; i < 48; ++i) { a[112 + i] = a[64 + i]; }
    REJECT(RB_CONFIG_PROFILE);
    a[112] ^= 1; seal(a); CHECK(DECODE() == 0 && r.config.count == 2);
    RESET(); a[78] = 2; seal(a); CHECK(DECODE() == 0 && r.config.entries[0].kind == 2);
    RESET(); a[79] = 0; a[80] = 0; seal(a); CHECK(DECODE() == 0 && r.config.entries[0].approved == 0);
    RESET(); a[36] = 0; put32(a + 40, 0); for (i = 64; i < 112; ++i) { a[i] = 0; }
    seal(a); CHECK(DECODE() == 0 && r.config.count == 0);
    RESET(); SELECT(3); CHECK(r.status == 0 && r.source == 0 && r.copies[0] == 0 && r.copies[1] == 0);
    put32(b + 16, 101); seal(b); SELECT(3); CHECK(r.status == 0 && r.source == 1 && r.config.generation == 101);
    put32(a + 16, 0xFFFFFFFFUL); seal(a); SELECT(3); CHECK(r.status == 0 && r.source == 0 && r.config.generation == 0xFFFFFFFFUL);
    RESET(); b[44] = 0; seal(b); SELECT(3); CHECK(r.status == RB_CONFIG_CONFLICT && r.source == RB_CONFIG_NONE && cleared(&r.config));
    RESET(); b[508] ^= 1; SELECT(3); CHECK(r.status == 0 && r.source == 0 && r.copies[1] == RB_CONFIG_CRC);
    RESET(); a[508] ^= 1; SELECT(3); CHECK(r.status == 0 && r.source == 1 && r.copies[0] == RB_CONFIG_CRC);
    b[508] ^= 1; SELECT(3); CHECK(r.status == RB_CONFIG_CRC && r.source == RB_CONFIG_NONE && cleared(&r.config));
    RESET(); SELECT(1); CHECK(r.status == 0 && r.source == 0 && r.copies[1] == RB_CONFIG_MISSING);
    SELECT(2); CHECK(r.status == 0 && r.source == 1 && r.copies[0] == RB_CONFIG_MISSING);
    SELECT(0); CHECK(r.status == RB_CONFIG_MISSING && r.source == RB_CONFIG_NONE && cleared(&r.config));
    /* Explicit v2 binding; legacy v1 remains diagnostic input only. */
    RESET(); a[8] = 2; put32(a + 108, 1); put32(a + 112, 0xFFFFFFFFUL);
    for (i = 0; i < 16; ++i) { a[48 + i] = i + 1; }
    seal(a); CHECK(DECODE() == 0 && r.config.version == 2 && r.config.media_id[15] == 16
          && r.config.entries[0].install_low == 1 && r.config.entries[0].install_high == 0xFFFFFFFFUL);
    for (i = 0; i < 16; ++i) { a[48 + i] = 0; } REJECT(RB_CONFIG_FORMAT);
    a[48] = 1; put32(a + 108, 0); put32(a + 112, 0); REJECT(RB_CONFIG_PROFILE);
    a[80] = 0; seal(a); CHECK(DECODE() == 0 && r.config.entries[0].install_low == 0);
    a[80] = 1; put32(a + 108, 1); put32(a + 112, 2);
    for (i = 1; i < 8; ++i) {
        rb_u16 j;
        for (j = 0; j < 52; ++j) { a[64 + i * 52 + j] = a[64 + j]; }
        put32(a + 64 + i * 52, i);
    }
    a[36] = 8; seal(a); CHECK(DECODE() == 0 && r.config.count == 8 && r.config.entries[7].install_high == 2
                           && r.config.entries[7].id == 7);
    a[480] = 1; REJECT(RB_CONFIG_FORMAT);
    a[480] = 0; a[47] = 1; REJECT(RB_CONFIG_FORMAT);
    a[47] = 0; a[8] = 3; REJECT(RB_CONFIG_FORMAT);
    report(n); return 0;
}
