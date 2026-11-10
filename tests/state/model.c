#include "state.h"
#include "state_fixture.h"
#include "handoff_fixture.h"

static rb_u8 a[512], b[512], mbr[512], ebr[512], vbr[512];
static rb_partition_scan scan;
static rb_config_result config;
static rb_state_result state;
static rb_state_proof proof;
static rb_u16 reads, target_reads, fault;

static void put32(rb_u8 *p, rb_u32 n)
{
    rb_u16 i;
    for (i = 0; i < 4; ++i) { p[i] = (rb_u8)n; n >>= 8; }
}
static void clear(void *p, rb_u16 length)
{
    rb_u8 *b = (rb_u8 *)p;
    while (length) { b[--length] = 0; }
}
static rb_u16 cleared(const rb_install_state *r)
{
    const rb_u8 *p = (const rb_u8 *)r;
    rb_u16 i;
    for (i = 0; i < sizeof(*r); ++i) { if (p[i]) { return 0; } }
    return 1;
}
static void seal(rb_u8 *p) { put32(p + 508, rb_crc32(p, 508)); }
static rb_u16 __cdecl read_mock(rb_u32 lba, rb_u8 *data, void *opaque)
{
    const rb_u8 *p;
    rb_u16 i;
    (void)opaque;
    ++reads;
    if (lba == 0) { p = mbr; }
    else if (lba == 63) { p = ebr; }
    else if (lba == 131072UL) { p = vbr; ++target_reads; }
    else { return 1; }
    if (fault == 1 || (fault == 2 && lba == 131072UL)) { return 1; }
    for (i = 0; i < 512; ++i) { data[i] = p[i]; }
    /* A second target read would observe different bytes. */
    if (target_reads > 1 && lba == 131072UL) { data[509] ^= 1; }
    return 0;
}
static void setup(void)
{
    rb_u16 i;
    reads = target_reads = fault = 0;
    clear(mbr, 512); clear(ebr, 512);
    for (i = 0; i < 512; ++i) { a[i] = b[i] = rb_state_vector[i]; vbr[i] = rb_test_vbr[i]; }
    for (i = 0; i < 16; ++i) { mbr[446 + i] = rb_test_entry[i]; }
    put32(mbr + 440, 0x52425431UL); mbr[510] = ebr[510] = 0x55; mbr[511] = ebr[511] = 0xAA;
    mbr[498] = 5; put32(mbr + 502, 63); put32(mbr + 506, 128520UL);
    ebr[450] = 0x16; put32(ebr + 454, 63); put32(ebr + 458, 128457UL);
    rb_scan_partitions(&scan, read_mock, (void *)0, 262144UL, 0, 0x52425431UL);
    rb_config_select(&config, rb_bound_config_vector, rb_bound_config_vector, 3, &scan, &scan.entries[4]);
    rb_state_select(&state, a, b, 3, &scan, &scan.entries[4]);
    reads = target_reads = 0;
}
static rb_u16 report(rb_u16 n)
{
    const char digits[] = "0123456789ABCDEF";
    rb_putc('R'); rb_putc('=');
    rb_putc(digits[(n >> 12) & 15]); rb_putc(digits[(n >> 8) & 15]);
    rb_putc(digits[(n >> 4) & 15]); rb_putc(digits[n & 15]); rb_putc(13); rb_putc(10);
    return n;
}
#define CHECK(c) do { ++n; if (!(c)) { return report(n); } } while (0)
#define DECODE() rb_state_decode(&state.state, a, 512, &scan, &scan.entries[4])
#define REJECT(c) do { seal(a); CHECK(DECODE() == (c) && cleared(&state.state)); } while (0)
#define SELECT(mask) rb_state_select(&state, a, b, mask, &scan, &scan.entries[4])
#define PROOF() rb_state_check(&proof, &config, &state, 0, read_mock, (void *)0, 262144UL, 0)
#define BLOCK(c) do { PROOF(); CHECK(proof.status == (c) && !proof.observed_crc && proof.matched_index == RB_CONFIG_NONE); } while (0)

rb_u16 __cdecl rb_state_selftest(void)
{
    rb_u16 n = 0, i;
    const rb_u16 format_offsets[] = {0, 7, 8, 10, 12, 16, 37, 38, 47, 128, 319, 320, 507};
    const rb_u16 profile_offsets[] = {80, 81, 82, 83, 88, 127};
    setup(); CHECK(scan.status == 0 && config.status == 0 && state.status == 0 && state.source == 0);
    CHECK(DECODE() == 0 && state.state.count == 1 && state.state.entries[0].phase == RB_INSTALL_READY);
    CHECK(rb_state_decode(&state.state, a, 511, &scan, &scan.entries[4]) == RB_CONFIG_FORMAT && cleared(&state.state));
    for (i = 0; i < sizeof(format_offsets) / sizeof(format_offsets[0]); ++i) {
        setup(); a[format_offsets[i]] ^= 1; REJECT(RB_CONFIG_FORMAT);
    }
    setup(); clear(a + 48, 16); REJECT(RB_CONFIG_FORMAT);
    setup(); a[508] ^= 1; CHECK(DECODE() == RB_CONFIG_CRC && cleared(&state.state));
    for (i = 20; i <= 32; i += 4) { setup(); a[i] ^= 1; REJECT(RB_CONFIG_IDENTITY); }
    setup(); scan.count = 21; REJECT(RB_CONFIG_IDENTITY);
    setup(); scan.ebr_count = 17; REJECT(RB_CONFIG_IDENTITY);
    for (i = 0; i < sizeof(profile_offsets) / sizeof(profile_offsets[0]); ++i) {
        setup(); a[profile_offsets[i]] = 0xFF; REJECT(RB_CONFIG_PROFILE);
    }
    setup(); clear(a + 64, 8); REJECT(RB_CONFIG_PROFILE);
    setup(); a[72] ^= 1; REJECT(RB_CONFIG_PROFILE);
    setup(); a[36] = 2; for (i = 0; i < 64; ++i) { a[128 + i] = a[64 + i]; } REJECT(RB_CONFIG_PROFILE);
    for (i = 1; i <= 7; ++i) {
        setup(); a[83] = (rb_u8)i; if (i != 6) { put32(a + 84, 0); }
        seal(a); CHECK(DECODE() == 0 && state.state.entries[0].phase == i);
    }
    setup(); a[83] = 5; REJECT(RB_CONFIG_PROFILE);
    setup(); put32(b + 16, 0xFFFFFFFFUL); seal(b); SELECT(3);
    CHECK(!state.status && state.source == 1 && state.state.generation == 0xFFFFFFFFUL);
    setup(); b[48] ^= 1; seal(b); SELECT(3); CHECK(state.status == RB_CONFIG_CONFLICT && cleared(&state.state));
    setup(); a[508] ^= 1; SELECT(3); CHECK(!state.status && state.source == 1 && state.copies[0] == RB_CONFIG_CRC);
    setup(); SELECT(0); CHECK(state.status == RB_CONFIG_MISSING && state.source == RB_CONFIG_NONE && cleared(&state.state));
    setup(); PROOF(); CHECK(!proof.status && proof.observed_crc == rb_crc32(vbr, 512) && proof.matched_index == 0);
    CHECK(reads == 3 && target_reads == 1);
    config.config.entries[0].id = 42; config.config.entries[0].name[0] = 'X'; config.config.generation = 99;
    target_reads = reads = 0; PROOF(); CHECK(!proof.status && target_reads == 1);
    setup(); config.status = RB_CONFIG_CRC; BLOCK(RB_PROOF_CONFIG); CHECK(!reads);
    setup(); state.status = RB_CONFIG_CONFLICT; BLOCK(RB_PROOF_STATE);
    setup(); config.copies[0] = RB_CONFIG_MISSING; BLOCK(RB_PROOF_DEGRADED);
    setup(); state.copies[1] = RB_CONFIG_IO; BLOCK(RB_PROOF_DEGRADED);
    setup(); config.config.version = 1; BLOCK(RB_PROOF_LEGACY);
    setup(); config.config.media_id[0] ^= 1; BLOCK(RB_PROOF_IDENTITY);
    setup(); config.config.layout_crc ^= 1; BLOCK(RB_PROOF_IDENTITY);
    setup(); config.config.count = 0; BLOCK(RB_PROOF_EMPTY);
    setup(); config.config.entries[0].install_high ^= 1; BLOCK(RB_PROOF_INSTALLATION);
    setup(); config.config.entries[0].kind = 2; BLOCK(RB_PROOF_TARGET);
    setup(); state.state.entries[0].phase = 1; BLOCK(RB_PROOF_NOT_READY);
    for (i = 2; i <= 7; ++i) {
        if (i == 6) { continue; }
        setup(); state.state.count = 2; state.state.entries[1].phase = i; BLOCK(RB_PROOF_PENDING); CHECK(!reads);
    }
    setup(); config.config.entries[0].approved = 0; BLOCK(RB_PROOF_APPROVAL);
    setup(); fault = 1; BLOCK(RB_PROOF_SCAN); CHECK(!target_reads);
    setup(); mbr[440] ^= 1; BLOCK(RB_PROOF_SCAN);
    setup(); mbr[458] ^= 1; BLOCK(RB_PROOF_LAYOUT); CHECK(!target_reads);
    setup(); mbr[446] = 0; mbr[450] = 0x16; PROOF(); CHECK(!proof.status && target_reads == 1);
    setup(); fault = 2; BLOCK(RB_PROOF_VOLUME);
    setup(); vbr[28] ^= 1; BLOCK(RB_PROOF_VOLUME);
    setup(); vbr[509] ^= 1; BLOCK(RB_PROOF_VBR);
    setup(); PROOF(); CHECK(!proof.status); vbr[510] = 0; BLOCK(RB_PROOF_VOLUME);
    setup(); put32(b + 16, 2); b[64] ^= 2; seal(b); SELECT(3); BLOCK(RB_PROOF_INSTALLATION);
    CHECK(state.source == 1 && !reads);
    setup(); put32(b + 16, 2); b[48] ^= 2; seal(b); SELECT(3); BLOCK(RB_PROOF_IDENTITY);
    CHECK(state.source == 1 && !reads);
    report(n); return 0;
}
