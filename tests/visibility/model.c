#include "visibility.h"
#include "state_fixture.h"
#include "handoff_fixture.h"

static rb_u8 mbr[512], ebr[512], vbr[512], cfg[512], record[512];
static rb_config_result config;
static rb_state_result state;
static rb_visibility_result result;
static rb_partition_scan scan;
static rb_u32 target_lba;
static rb_u16 reads, mbr_reads, target_reads, fault;

static void put32(rb_u8 *p, rb_u32 n)
{
    rb_u16 i;
    for (i = 0; i < 4; ++i) { p[i] = (rb_u8)n; n >>= 8; }
}

static void seal(rb_u8 *p) { put32(p + 508, rb_crc32(p, 508)); }

static rb_u16 __cdecl read_mock(rb_u32 lba, rb_u8 *data, void *opaque)
{
    const rb_u8 *source;
    rb_u16 i;
    (void)opaque;

    ++reads;
    if (lba == 0) { source = mbr; ++mbr_reads; }
    else if (lba == 63) { source = ebr; }
    else if (lba == target_lba) { source = vbr; ++target_reads; }
    else { return 1; }

    if (fault == 1 || (fault == 2 && lba == target_lba)) { return 1; }
    for (i = 0; i < 512; ++i) { data[i] = source[i]; }

    /* A second MBR read would no longer describe the tested medium. */
    if (mbr_reads > 1 && lba == 0) { data[510] = 0; }
    return 0;
}

static void bind_records(void)
{
    rb_u16 i;
    rb_u32 layout;

    reads = mbr_reads = target_reads = 0;
    rb_scan_partitions(&scan, read_mock, (void *)0, 262144UL, 0, 0x52425431UL);
    layout = rb_layout_crc(&scan);

    for (i = 0; i < 512; ++i) { cfg[i] = rb_bound_config_vector[i]; record[i] = rb_state_vector[i]; }
    put32(cfg + 24, layout); seal(cfg);
    put32(record + 24, layout); seal(record);
    rb_config_select(&config, cfg, cfg, 3, &scan, &scan.entries[4]);
    rb_state_select(&state, record, record, 3, &scan, &scan.entries[4]);
    reads = mbr_reads = target_reads = 0;
}

static void setup(void)
{
    rb_u16 i;

    fault = 0; target_lba = 131072UL;
    for (i = 0; i < 512; ++i) { mbr[i] = ebr[i] = 0; vbr[i] = rb_test_vbr[i]; }
    for (i = 0; i < 446; ++i) { mbr[i] = (rb_u8)(i ^ 0xA5); }
    for (i = 0; i < 16; ++i) { mbr[446 + i] = rb_test_entry[i]; }

    mbr[432] = 'R'; mbr[433] = 'B'; mbr[434] = 'M'; mbr[435] = '1';
    put32(mbr + 436, 126); put32(mbr + 440, 0x52425431UL);
    mbr[466] = 6; put32(mbr + 470, 140000UL); put32(mbr + 474, 5073);
    mbr[482] = 0x17; put32(mbr + 486, 150000UL); put32(mbr + 490, 5073);
    mbr[498] = 5; put32(mbr + 502, 63); put32(mbr + 506, 128520UL);
    ebr[450] = 0x16; put32(ebr + 454, 63); put32(ebr + 458, 128457UL);
    mbr[510] = ebr[510] = 0x55; mbr[511] = ebr[511] = 0xAA;
    bind_records();
}

static rb_u16 cleared(void)
{
    rb_u16 i;

    if (result.current_visible || result.current_active || result.wanted_visible
            || result.wanted_active || result.changed) { return 0; }
    for (i = 0; i < 512; ++i) {
        if (result.before[i] || result.after[i]) { return 0; }
    }
    return 1;
}

static rb_u16 preserved(void)
{
    rb_u16 i, field;

    for (i = 0; i < 512; ++i) {
        if (result.before[i] != mbr[i]) { return 0; }
        field = i >= 446 && i < 510 && ((i - 446) % 16 == 0 || (i - 446) % 16 == 4);
        if (!field && result.after[i] != mbr[i]) { return 0; }
    }
    for (i = 494; i < 510; ++i) { if (result.after[i] != mbr[i]) { return 0; } }
    return 1;
}

static rb_u16 report(rb_u16 n)
{
    const char digits[] = "0123456789ABCDEF";

    rb_putc('P'); rb_putc('=');
    rb_putc(digits[(n >> 12) & 15]); rb_putc(digits[(n >> 8) & 15]);
    rb_putc(digits[(n >> 4) & 15]); rb_putc(digits[n & 15]); rb_putc(13); rb_putc(10);
    return n;
}

#define CHECK(c) do { ++n; if (!(c)) { return report(n); } } while (0)
#define PREVIEW() rb_visibility_check(&result, &config, &state, 0, read_mock, (void *)0, 262144UL, 0, 126)
#define BLOCK(code) do { PREVIEW(); CHECK(result.status == (code) && cleared()); } while (0)

rb_u16 __cdecl rb_visibility_selftest(void)
{
    const rb_u16 types[] = {6, 14, 11, 12, 7};
    rb_u16 n = 0, i;
    rb_u8 *bytes;

    setup(); CHECK(!config.status && !state.status && !scan.status);
    PREVIEW(); CHECK(result.status == RB_VISIBILITY_CHANGE && !result.proof.status);
    CHECK(result.current_visible == 3 && result.current_active == 1
        && result.wanted_visible == 1 && result.wanted_active == 1 && result.changed == 2);
    CHECK(result.after[466] == 0x16 && result.after[482] == 0x17 && preserved());
    CHECK(reads == 3 && mbr_reads == 1 && target_reads == 1);

    setup(); mbr[466] = 0x16; PREVIEW();
    CHECK(result.status == RB_VISIBILITY_MATCH && !result.changed && preserved());
    setup(); mbr[446] = 0; mbr[450] = 0x16; mbr[462] = 0x80; PREVIEW();
    CHECK(result.status == RB_VISIBILITY_CHANGE && result.current_active == 2 && result.changed == 3);
    CHECK(result.after[446] == 0x80 && result.after[462] == 0 && result.after[450] == 6 && preserved());
    setup(); mbr[446] = 0; PREVIEW(); CHECK(result.changed == 3 && result.wanted_active == 1 && preserved());

    setup(); config.config.entries[0].kind = state.state.entries[0].kind = 2;
    config.config.entries[0].visible_mask = 3; PREVIEW();
    CHECK(result.status == RB_VISIBILITY_MATCH && result.wanted_visible == 3 && preserved());
    setup(); config.config.entries[0].kind = state.state.entries[0].kind = 2;
    config.config.entries[0].visible_mask = 7; PREVIEW();
    CHECK(result.status == RB_VISIBILITY_CHANGE && result.changed == 4 && result.after[482] == 7 && preserved());

    for (i = 0; i < 5; ++i) {
        setup(); mbr[466] = (rb_u8)types[i]; bind_records(); PREVIEW();
        CHECK(result.status == RB_VISIBILITY_CHANGE && result.after[466] == types[i] + 0x10 && preserved());

        setup(); mbr[466] = (rb_u8)(types[i] + 0x10); bind_records();
        config.config.entries[0].kind = state.state.entries[0].kind = 2;
        config.config.entries[0].visible_mask = 3; PREVIEW();
        CHECK(result.status == RB_VISIBILITY_CHANGE && result.after[466] == types[i] && preserved());
    }

    setup(); target_lba = 140000UL; put32(vbr + 28, target_lba);
    config.config.entries[0].slot = state.state.entries[0].slot = 2;
    config.config.entries[0].start = state.state.entries[0].start = target_lba;
    config.config.entries[0].visible_mask = 2;
    state.state.entries[0].vbr_crc = rb_crc32(vbr, 512); PREVIEW();
    CHECK(result.wanted_visible == 2 && result.wanted_active == 2 && result.changed == 3);
    CHECK(result.after[450] == 0x16 && result.after[446] == 0 && result.after[462] == 0x80 && preserved());

    setup(); ebr[450] = 6; BLOCK(RB_VISIBILITY_ADMIN); CHECK(result.error_lba == 126);
    setup(); mbr[436] ^= 1; BLOCK(RB_VISIBILITY_ADMIN); CHECK(result.error_lba == 0);
    setup(); mbr[432] ^= 1; BLOCK(RB_VISIBILITY_ADMIN);
    setup(); config.config.entries[0].visible_mask = 3; BLOCK(RB_VISIBILITY_PROOF);
    CHECK(result.proof.status == RB_PROOF_CONFIG && result.proof.detail == RB_CONFIG_PROFILE);
    setup(); config.config.entries[0].visible_mask = 0; BLOCK(RB_VISIBILITY_PROOF);
    setup(); config.config.entries[0].kind = state.state.entries[0].kind = 2;
    config.config.entries[0].visible_mask = 9; BLOCK(RB_VISIBILITY_PROOF);

    setup(); config.config.count = 0; BLOCK(RB_VISIBILITY_PROOF);
    CHECK(result.proof.status == RB_PROOF_EMPTY && !reads);
    setup(); state.copies[1] = RB_CONFIG_CRC; BLOCK(RB_VISIBILITY_PROOF); CHECK(!reads);
    setup(); state.state.entries[0].phase = RB_INSTALL_RECOVERY; BLOCK(RB_VISIBILITY_PROOF); CHECK(!reads);
    setup(); mbr[462] = 0x80; BLOCK(RB_VISIBILITY_PROOF); CHECK(result.proof.status == RB_PROOF_SCAN);
    setup(); mbr[482] = 0x83; BLOCK(RB_VISIBILITY_PROOF);
    setup(); mbr[498] = 0x85; BLOCK(RB_VISIBILITY_PROOF);
    setup(); fault = 1; BLOCK(RB_VISIBILITY_PROOF); CHECK(!target_reads);
    setup(); fault = 2; BLOCK(RB_VISIBILITY_PROOF); CHECK(result.error_lba == target_lba);
    setup(); vbr[509] ^= 1; BLOCK(RB_VISIBILITY_PROOF); CHECK(result.proof.status == RB_PROOF_VBR);

    setup(); PREVIEW(); CHECK(result.status == RB_VISIBILITY_CHANGE);
    reads = mbr_reads = target_reads = 0; vbr[510] = 0; BLOCK(RB_VISIBILITY_PROOF);
    CHECK(result.proof.observed_crc == 0 && result.proof.matched_index == RB_CONFIG_NONE);

    setup(); fault = 2;
    rb_state_check_layout(&result.proof, &scan, &config, &state, 0, read_mock, (void *)0, 262144UL, 0);
    bytes = (rb_u8 *)&scan;
    for (i = 0; i < sizeof(scan); ++i) { if (bytes[i]) { return report(n + 1); } }
    CHECK(result.proof.status == RB_PROOF_VOLUME);

    report(n);
    return 0;
}
