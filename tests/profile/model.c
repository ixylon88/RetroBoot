#include "profile_test.h"
#include "state_fixture.h"
#include "handoff_fixture.h"

static rb_u8 mbr[512], ebr[512], vbr[512], cfg[512], record[512];
static rb_config_result config;
static rb_state_result state;
static rb_visibility_result visibility;
static rb_handoff_buffer prepared;
static rb_partition_scan scan;
static rb_profile_selection selected;
static rb_u16 reads, mbr_reads, vbr_reads, fault;

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
    else if (lba == 131072UL) { source = vbr; ++vbr_reads; }
    else { return 1; }
    if (fault == 1 || (fault == 2 && lba == 131072UL)) { return 1; }
    for (i = 0; i < 512; ++i) { data[i] = source[i]; }

    /* A redundant read must not silently become the executed observation. */
    if ((lba == 0 && mbr_reads > 1) || (lba == 131072UL && vbr_reads > 1)) { data[510] = 0; }
    return 0;
}

static void bind(void)
{
    rb_u16 i;
    rb_u32 layout;
    reads = mbr_reads = vbr_reads = 0;
    rb_scan_partitions(&scan, read_mock, (void *)0, 262144UL, 0, 0x52425431UL);
    layout = rb_layout_crc(&scan);
    for (i = 0; i < 512; ++i) { cfg[i] = rb_bound_config_vector[i]; record[i] = rb_state_vector[i]; }
    put32(cfg + 24, layout); seal(cfg); put32(record + 24, layout); seal(record);
    rb_config_select(&config, cfg, cfg, 3, &scan, &scan.entries[4]);
    rb_state_select(&state, record, record, 3, &scan, &scan.entries[4]);
    reads = mbr_reads = vbr_reads = 0;
}

static void setup(void)
{
    rb_u16 i;
    fault = 0;
    for (i = 0; i < 512; ++i) { mbr[i] = ebr[i] = 0; vbr[i] = rb_test_vbr[i]; }
    for (i = 0; i < 16; ++i) { mbr[446 + i] = rb_test_entry[i]; }
    mbr[432] = 'R'; mbr[433] = 'B'; mbr[434] = 'M'; mbr[435] = '1';
    put32(mbr + 436, 126); put32(mbr + 440, 0x52425431UL);
    mbr[498] = 5; put32(mbr + 502, 63); put32(mbr + 506, 128520UL);
    ebr[450] = 0x16; put32(ebr + 454, 63); put32(ebr + 458, 128457UL);
    mbr[510] = ebr[510] = 0x55; mbr[511] = ebr[511] = 0xAA;
    bind();
}

static rb_u16 cleared(void)
{
    rb_u16 i;
    const rb_u8 *bytes = (const rb_u8 *)&prepared;
    for (i = 0; i < 528; ++i) { if (bytes[i]) { return 0; } }
    return prepared.detail == 0;
}

static rb_u16 exact(void)
{
    rb_u16 i;
    for (i = 0; i < 512; ++i) { if (prepared.sector[i] != rb_test_vbr[i]) { return 0; } }
    for (i = 0; i < 16; ++i) { if (prepared.entry[i] != rb_test_entry[i]) { return 0; } }
    return 1;
}

static rb_u16 report(rb_u16 n)
{
    const char digits[] = "0123456789ABCDEF";
    rb_putc('J'); rb_putc('=');
    rb_putc(digits[(n >> 12) & 15]); rb_putc(digits[(n >> 8) & 15]);
    rb_putc(digits[(n >> 4) & 15]); rb_putc(digits[n & 15]); rb_putc(13); rb_putc(10);
    return n;
}

#define CHECK(c) do { ++n; if (!(c)) { return report(n); } } while (0)
#define PREPARE() rb_prepare_profile_test(&prepared, &visibility, &config, &state, 0, read_mock, (void *)0, 262144UL, 0, 126)
#define REJECT(code) CHECK(PREPARE() == (code) && prepared.status == (code) && cleared())
#define REMEMBER() rb_profile_remember(&selected, &config, 0)
#define RESELECT() rb_profile_reselect(&selected, &config, &index)
#define CHANGED(field) do { setup(); REMEMBER(); ++config.config.entries[0].field; CHECK(!RESELECT() && index == RB_CONFIG_NONE); } while (0)

rb_u16 __cdecl rb_profile_test_selftest(void)
{
    rb_u16 n = 0, i, index;
    setup(); CHECK(!config.status && !state.status);
    CHECK(PREPARE() == 0 && !prepared.status && exact());
    CHECK(reads == 3 && mbr_reads == 1 && vbr_reads == 1);

    /* Changed metadata cannot authorize a different executable sector. */
    setup(); vbr[509] ^= 1; REJECT(RB_PROFILE_TEST_PROOF);
    CHECK(visibility.proof.status == RB_PROOF_VBR);
    setup(); vbr[509] ^= 1; state.state.entries[0].vbr_crc = rb_crc32(vbr, 512);
    REJECT(RB_PROFILE_TEST_CODE); CHECK(!visibility.proof.status && vbr_reads == 1);
    setup(); mbr[447] ^= 1; REJECT(RB_PROFILE_TEST_TARGET);
    CHECK(!visibility.proof.status && !visibility.status);
    setup(); mbr[440] ^= 1; config.config.disk_id ^= 1; state.state.disk_id ^= 1;
    REJECT(RB_PROFILE_TEST_TARGET);

    setup(); mbr[446] = 0; REJECT(RB_PROFILE_TEST_CHANGE);
    setup(); mbr[450] = 0x16; REJECT(RB_PROFILE_TEST_CHANGE);
    setup(); mbr[466] = 6; put32(mbr + 470, 140000UL); put32(mbr + 474, 5073); bind();
    REJECT(RB_PROFILE_TEST_CHANGE); CHECK(visibility.changed == 2);
    reads = mbr_reads = vbr_reads = 0;
    config.config.entries[0].kind = state.state.entries[0].kind = 2;
    config.config.entries[0].visible_mask = 3;
    CHECK(PREPARE() == 0 && exact());

    /* The vectors name P1, so rebuild their decoded identity for P2 here. */
    setup();
    for (i = 0; i < 16; ++i) { mbr[462 + i] = mbr[446 + i]; mbr[446 + i] = 0; }
    reads = mbr_reads = vbr_reads = 0;
    rb_scan_partitions(&scan, read_mock, (void *)0, 262144UL, 0, 0x52425431UL);
    config.config.layout_crc = state.state.layout_crc = rb_layout_crc(&scan);
    config.config.entries[0].slot = state.state.entries[0].slot = 2;
    config.config.entries[0].visible_mask = 2;
    reads = mbr_reads = vbr_reads = 0;
    REJECT(RB_PROFILE_TEST_TARGET); CHECK(!visibility.status);

    setup(); state.copies[0] = RB_CONFIG_CRC; REJECT(RB_PROFILE_TEST_PROOF); CHECK(!reads);
    setup(); state.state.entries[0].phase = RB_INSTALL_RECOVERY; REJECT(RB_PROFILE_TEST_PROOF); CHECK(!reads);
    setup(); config.config.entries[0].approved = 0; REJECT(RB_PROFILE_TEST_PROOF); CHECK(!reads);
    setup(); state.state.entries[0].install_low ^= 2; REJECT(RB_PROFILE_TEST_PROOF); CHECK(!reads);
    setup(); fault = 1; REJECT(RB_PROFILE_TEST_PROOF); CHECK(!vbr_reads);
    setup(); fault = 2; REJECT(RB_PROFILE_TEST_PROOF); CHECK(visibility.error_lba == 131072UL);
    setup(); mbr[436] ^= 1; REJECT(RB_PROFILE_TEST_PROOF); CHECK(visibility.status == RB_VISIBILITY_ADMIN);
    setup(); CHECK(PREPARE() == 0); reads = mbr_reads = vbr_reads = 0;
    state.state.entries[0].phase = RB_INSTALL_VERIFY; REJECT(RB_PROFILE_TEST_PROOF);

    setup(); REMEMBER(); CHECK(selected.valid && RESELECT() && index == 0);
    ++config.config.generation; CHECK(RESELECT() && index == 0);
    config.config.entries[1] = config.config.entries[0];
    config.config.entries[0].id = 2; config.config.entries[0].name[0] = 'X'; config.config.count = 2;
    CHECK(RESELECT() && index == 1);
    config.config.entries[0] = config.config.entries[1]; CHECK(!RESELECT() && index == RB_CONFIG_NONE);
    CHANGED(id); CHANGED(start); CHANGED(sectors); CHANGED(install_low); CHANGED(install_high);
    CHANGED(slot); CHANGED(type); CHANGED(kind); CHANGED(installed); CHANGED(approved); CHANGED(visible_mask);
    setup(); REMEMBER(); config.config.entries[0].name[0] ^= 1; CHECK(!RESELECT());
    setup(); REMEMBER(); config.config.media_id[0] ^= 1; CHECK(!RESELECT());
    setup(); REMEMBER(); ++config.config.disk_id; CHECK(!RESELECT());
    setup(); REMEMBER(); ++config.config.layout_crc; CHECK(!RESELECT());
    setup(); REMEMBER(); config.config.count = 0; CHECK(!RESELECT());
    setup(); REMEMBER(); config.status = RB_CONFIG_CRC; CHECK(!RESELECT());
    setup(); REMEMBER(); config.config.version = 1; CHECK(!RESELECT());
    setup(); REMEMBER(); config.config.count = 9; CHECK(!RESELECT());
    setup(); config.config.count = 0; REMEMBER(); CHECK(!selected.valid && !RESELECT());
    setup(); config.config.count = 9; REMEMBER(); CHECK(!selected.valid);
    setup(); config.config.version = 1; REMEMBER(); CHECK(!selected.valid);
    setup(); rb_profile_remember(&selected, &config, 1); CHECK(!selected.valid);
    report(n);
    return 0;
}
