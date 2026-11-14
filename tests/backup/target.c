#include "backup_target.h"
#include "config.h"
#include "journal_io_fixture.h"

static rb_u8 mbr[512], ebr[512], vbr[512], root[1024];
static struct { rb_u32 before; rb_backup_target result; rb_u32 after; } guarded;
static rb_backup claims;
static rb_rescue_device device;
static rb_u16 io_call, change_pass, pass_changed;
static rb_u32 requested[2048];
static rb_u8 records[4][512];
static rb_u16 changing_mbr, payload_reads;
static struct { rb_u16 cluster, value; } values[132];
static rb_u16 value_count, reads, mbr_reads, vbr_reads;
static rb_u16 mirror, unexpected;

static void put16(rb_u8 *p, rb_u16 n) { p[0] = (rb_u8)n; p[1] = (rb_u8)(n >> 8); }
static void put32(rb_u8 *p, rb_u32 n) { put16(p, (rb_u16)n); put16(p + 2, (rb_u16)(n >> 16)); }
static void seal(void)
{
    rb_u16 i, sum = 0;
    put16(vbr + 72, 0);
    for (i = 0; i < 512; i += 2) { sum += vbr[i] | ((rb_u16)vbr[i + 1] << 8); }
    put16(vbr + 72, (rb_u16)(0U - sum));
}
static void fat(rb_u16 cluster, rb_u16 value)
{
    rb_u16 i;
    for (i = 0; i < value_count; ++i) {
        if (values[i].cluster == cluster) { values[i].value = value; return; }
    }
    values[value_count].cluster = cluster; values[value_count++].value = value;
}
static void entry(rb_u16 index, const char *name, rb_u16 cluster, rb_u32 bytes)
{
    rb_u16 i;
    rb_u8 *p = root + index * 32;
    for (i = 0; i < 32; ++i) { p[i] = 0; }
    for (i = 0; i < 11; ++i) { p[i] = name[i]; }
    p[11] = 0x20; put16(p + 26, cluster); put32(p + 28, bytes);
}
static rb_u16 __cdecl read_mock(rb_u32 lba, rb_u8 *data, void *opaque)
{
    const rb_u8 *source = (const rb_u8 *)0;
    rb_u16 i, index, copy;
    if (reads >= 2048 || opaque != (void *)&device) { ++unexpected; return 1; }
    requested[reads++] = lba;
    if (reads == io_call) { return 1; }
    if (!lba && mbr_reads == 3 && change_pass && !pass_changed) {
        pass_changed = 1;
        if (change_pass == 1) { mbr[100] ^= 1; }
        if (change_pass == 2) { ebr[447] ^= 1; }
        if (change_pass == 3) { vbr[8] ^= 1; seal(); }
        if (change_pass == 4) { root[14] ^= 1; }
        if (change_pass == 5) {
            put32(records[0] + 16, 2); put32(records[1] + 16, 2);
            put32(records[0] + 508, rb_crc32(records[0], 508));
            put32(records[1] + 508, rb_crc32(records[1], 508));
        }
    }
    for (i = 0; i < 512; ++i) { data[i] = 0; }
    if (!lba) { source = mbr; ++mbr_reads; }
    else if (lba == 63) { source = ebr; }
    else if (lba == 126) { source = vbr; ++vbr_reads; }
    else if (lba >= 379 && lba <= 410) {
        if (lba < 381) { source = root + (rb_u16)(lba - 379) * 512; }
    } else if (lba >= 127 && lba < 379) {
        copy = lba >= 253; index = (rb_u16)(lba - (copy ? 253 : 127));
        if (!index) { put16(data, 0xFFF8); put16(data + 2, 0xFFFF); }
        for (i = 0; i < value_count; ++i) {
            if (values[i].cluster / 256 == index) { put16(data + (values[i].cluster % 256) * 2, values[i].value); }
        }
        if (change_pass == 6 && pass_changed && index == 125) { data[511] ^= 1; }
        if (mirror && copy && index == 125) { data[511] ^= 1; }
    } else {
        for (i = 0; i < 4; ++i) {
            if (lba == 3209UL + i * 100UL) { source = records[i]; ++payload_reads; }
        }
        if (!source) { ++unexpected; return 1; }
    }
    if (source) { for (i = 0; i < 512; ++i) { data[i] = source[i]; } }
    if (!lba && mbr_reads > 1 && changing_mbr) { data[100] ^= 1; }
    return 0;
}
static void setup_disk(void)
{
    rb_u16 i;
    io_call = change_pass = pass_changed = 0;
    reads = mbr_reads = vbr_reads = value_count = changing_mbr = payload_reads = 0;
    mirror = unexpected = 0;
    for (i = 0; i < 512; ++i) { mbr[i] = ebr[i] = vbr[i] = 0; }
    for (i = 0; i < 1024; ++i) { root[i] = 0; }
    ebr[450] = 0x16; put32(ebr + 454, 63); put32(ebr + 458, 5285UL);
    ebr[510] = vbr[510] = 0x55; ebr[511] = vbr[511] = 0xAA;
    vbr[0] = 0xEB; vbr[2] = 0x90; put16(vbr + 11, 512); vbr[13] = 1;
    put16(vbr + 14, 1); vbr[16] = 2; put16(vbr + 17, 512); vbr[21] = 0xF8;
    put16(vbr + 22, 126); put32(vbr + 28, 126); put32(vbr + 32, 5285UL);
    vbr[62] = 'R'; vbr[63] = 'B'; vbr[64] = 'V'; vbr[65] = '1';
    put32(vbr + 66, 411); put16(vbr + 70, 3); seal();
    entry(0, "RBBOOT  SYS", 2, 1536);
    for (i = 1; i < 20; ++i) { root[i * 32] = 0xE5; }
    entry(20, "RBSTG2  BIN", 20, 5000);
    entry(21, "RBCFG   A  ", 2800, 512); entry(22, "RBCFG   B  ", 2900, 512);
    entry(23, "RBSTATE A  ", 3000, 512); entry(24, "RBSTATE B  ", 3100, 512);
    entry(25, "RBTXN   A  ", 3200, 1536); entry(26, "RBTXN   B  ", 3300, 1536);
    fat(2, 3); fat(3, 4); fat(4, 0xFFFF);
    for (i = 20; i < 30; ++i) { fat(i, i == 29 ? 0xFFFF : i + 1); }
    fat(2800, 0xFFFF); fat(2900, 0xFFFF); fat(3000, 0xFFFF); fat(3100, 0xFFFF); fat(3200, 3202); fat(3202, 3204); fat(3204, 0xFFFF);
    fat(3300, 3302); fat(3302, 3304); fat(3304, 0xFFFF);
    for (i = 0; i < 512; ++i) {
        mbr[i] = rb_io_journal[512 + i];
        records[0][i] = records[1][i] = rb_io_config[i]; records[2][i] = records[3][i] = rb_io_state[i];
    }
}

static rb_u32 get32(const rb_u8 *p)
{
    return (rb_u32)p[0] | ((rb_u32)p[1] << 8) | ((rb_u32)p[2] << 16) | ((rb_u32)p[3] << 24);
}
static void setup(void)
{
    rb_u16 i;
    setup_disk();
    for (i = 0; i < sizeof(claims); ++i) { ((rb_u8 *)&claims)[i] = 0; }
    claims.generation = 1; claims.disk_id = 0x52425431UL;
    claims.layout_crc = get32(records[0] + 24); claims.admin_start = 126; claims.admin_sectors = 5285;
    claims.capacity_low = 262144UL; claims.route = 1;
    for (i = 0; i < 16; ++i) { claims.media_id[i] = records[0][48 + i]; }
    device.drive = 0x80; device.mode = 1; device.heads = device.sectors_per_track = 0;
    device.capacity_low = 262144UL; device.capacity_high = 0;
}
static void run(void)
{
    rb_u16 i;
    guarded.before = 0x12345678UL; guarded.after = 0x87654321UL;
    for (i = 0; i < sizeof(guarded.result); ++i) { ((rb_u8 *)&guarded.result)[i] = 0xA5; }
    rb_backup_match_target(&guarded.result, &claims, &device, read_mock, &device);
}
static rb_u16 guards(void)
{
    return guarded.before == 0x12345678UL && guarded.after == 0x87654321UL && !unexpected;
}
static rb_u16 cleared(void)
{
    rb_u16 i;
    const rb_u8 *p = (const rb_u8 *)&guarded.result;
    for (i = 8; i < sizeof(guarded.result); ++i) { if (p[i]) { return 0; } }
    return guards();
}
static void hex(rb_u16 value)
{
    rb_u16 i;
    static const char digits[] = "0123456789ABCDEF";
    for (i = 4; i; ) { --i; rb_putc(digits[(value >> (i * 4)) & 15]); }
}
static rb_u16 report(rb_u16 n, rb_u16 failed)
{
    rb_putc(failed ? '!' : 'F'); rb_putc('='); hex(n); rb_putc(13); rb_putc(10);
    return failed;
}
static void record_crc(rb_u8 *p) { put32(p + 508, rb_crc32(p, 508)); }
#define CHECK(c) do { ++n; if (!(c)) { \
    rb_putc('@'); hex(__LINE__); rb_putc(':'); hex(guarded.result.status); \
    rb_putc('/'); hex(guarded.result.detail); rb_putc(13); rb_putc(10); \
    return report(n, 1); } } while (0)
#define BLOCK(c) do { run(); CHECK(guarded.result.status == (c) && cleared()); } while (0)

rb_u16 __cdecl rb_backup_target_selftest(void)
{
    rb_u16 n = 0, i, j, total, pass;
    rb_u16 faults[20];
    rb_backup_target *r = &guarded.result;
    setup(); run();
    CHECK(!r->status && guards() && r->disk_id == claims.disk_id && r->layout_crc == claims.layout_crc);
    CHECK(r->admin_start == 126 && r->admin_sectors == 5285 && r->config_generation == 1 && r->state_generation == 1);
    CHECK(mbr_reads == 6 && vbr_reads == 2 && payload_reads == 8 && reads < 2048 && !(reads & 1));
    total = reads; pass = reads / 2;
    for (i = 0; i < 16; ++i) { CHECK(r->media_id[i] == claims.media_id[i]); }
    for (i = 0; i < pass; ++i) { if (requested[i] != requested[pass + i]) { return report(n, 1); } }
    CHECK(requested[0] == 0 && requested[1] == 0 && requested[2] == 63 && requested[3] == 126);
    CHECK(requested[pass - 5] == 3209 && requested[pass - 4] == 3309
        && requested[pass - 3] == 3409 && requested[pass - 2] == 3509 && !requested[pass - 1]);
    /* The complete successful physical-address sequence is independently
       checked by the host runner, not inferred from the native status. */
    rb_putc('L'); rb_putc('=');
    for (i = 0; i < reads; ++i) { hex((rb_u16)(requested[i] >> 16)); hex((rb_u16)requested[i]); rb_putc(','); }
    rb_putc(13); rb_putc(10);

    setup(); device.mode = 0; claims.route = 2;
    claims.heads = device.heads = 16; claims.sectors_per_track = device.sectors_per_track = 63;
    run(); CHECK(!r->status && guards() && reads == total);
    setup(); claims.capacity_low = device.capacity_low = 0; claims.capacity_high = device.capacity_high = 1;
    run(); CHECK(!r->status && guards() && reads == total);
    setup(); claims.heads = device.heads = 255; claims.sectors_per_track = device.sectors_per_track = 63;
    run(); CHECK(!r->status && guards());
    setup(); claims.entries[0].lba = 0xFFFFFF00UL; claims.entries[0].sectors = 50;
    run(); CHECK(!r->status && guards() && reads == total);
    setup(); claims.disk_id ^= 1; BLOCK(RB_BTARGET_IDENTITY); CHECK(r->detail == 4 && reads == total);
    setup(); claims.media_id[15] ^= 1; BLOCK(RB_BTARGET_IDENTITY); CHECK(r->detail == 4 && reads == total);
    setup(); claims.layout_crc ^= 1; BLOCK(RB_BTARGET_LAYOUT); CHECK(reads == total);
    setup(); claims.admin_start = 127; BLOCK(RB_BTARGET_LAYOUT); CHECK(reads == total);
    setup(); ++claims.admin_sectors; BLOCK(RB_BTARGET_LAYOUT); CHECK(reads == total);
    setup(); ++device.capacity_low; BLOCK(RB_BTARGET_CAPACITY); CHECK(!reads);
    setup(); device.capacity_high = 1; BLOCK(RB_BTARGET_CAPACITY); CHECK(!reads);
    setup(); device.mode = 0; device.heads = 16; device.sectors_per_track = 63;
    BLOCK(RB_BTARGET_GEOMETRY); CHECK(!reads);
    setup(); device.heads = 16; device.sectors_per_track = 63; BLOCK(RB_BTARGET_GEOMETRY); CHECK(!reads);
    setup(); claims.heads = 16; claims.sectors_per_track = 63; BLOCK(RB_BTARGET_GEOMETRY); CHECK(!reads);

    for (i = 0; i < 9; ++i) {
        setup();
        if (i == 0) { claims.disk_id = 0; }
        if (i == 1) { for (j = 0; j < 16; ++j) { claims.media_id[j] = 0; } }
        if (i == 2) { claims.admin_start = 0; }
        if (i == 3) { claims.admin_sectors = 0; }
        if (i == 4) { claims.admin_start = 0xFFFFFF00UL; }
        if (i == 5) { claims.admin_sectors = 262144UL; }
        if (i == 6) { claims.route = 0; }
        if (i == 7) { claims.heads = 1; }
        if (i == 8) { claims.route = 2; }
        BLOCK(RB_BTARGET_PARAMS); CHECK(r->detail == 1 && !reads);
    }
    for (i = 0; i < 8; ++i) {
        setup();
        if (i == 0) { device.drive = 0; }
        if (i == 1) { device.mode = 2; }
        if (i == 2) { device.capacity_low = 0; }
        if (i == 3) { device.heads = 1; }
        if (i == 4) { device.heads = 257; device.sectors_per_track = 63; }
        if (i == 5) { device.heads = 16; device.sectors_per_track = 64; }
        if (i == 6) { device.mode = 0; }
        if (i == 7) { device.mode = 0; device.heads = 1; device.sectors_per_track = 1; }
        BLOCK(RB_BTARGET_PARAMS); CHECK(r->detail == 2 && !reads);
    }
    setup(); rb_backup_match_target(r, (const rb_backup *)0, &device, read_mock, &device);
    CHECK(r->status == RB_BTARGET_PARAMS && cleared() && !reads);
    setup(); rb_backup_match_target(r, &claims, (const rb_rescue_device *)0, read_mock, &device);
    CHECK(r->status == RB_BTARGET_PARAMS && cleared() && !reads);
    setup(); rb_backup_match_target(r, &claims, &device, (rb_sector_reader)0, &device);
    CHECK(r->status == RB_BTARGET_PARAMS && cleared() && !reads);

    for (i = 0; i < 4; ++i) {
        setup();
        if (i == 0) { mbr[510] = 0; }
        if (i == 1) { mbr[432] = 0; }
        if (i == 2) { put32(mbr + 436, 0); }
        if (i == 3) { put32(mbr + 440, 0); }
        BLOCK(RB_BTARGET_IDENTITY); CHECK(r->detail == 1 && reads == 1);
    }
    setup(); root[800] = 0xE5; BLOCK(RB_BTARGET_ALLOCATION); CHECK(!payload_reads);
    setup(); mirror = 1; BLOCK(RB_BTARGET_ALLOCATION); CHECK(!payload_reads);
    setup(); mbr[498] = 0xEE; BLOCK(RB_BTARGET_ALLOCATION); CHECK(!payload_reads);
    setup(); changing_mbr = 1; BLOCK(RB_BTARGET_CHANGED); CHECK(!payload_reads);

    for (i = 0; i < 4; ++i) {
        setup(); records[i][80] ^= 1;
        BLOCK(i < 2 ? RB_BTARGET_CONFIG : RB_BTARGET_STATE);
        CHECK(r->detail == 4 && r->error_lba == 3209UL + i * 100UL);
    }
    for (i = 0; i < 4; ++i) {
        setup(); records[i][48] ^= 1; put32(records[i] + 16, 2); record_crc(records[i]);
        BLOCK(RB_BTARGET_IDENTITY); CHECK(r->detail == (i < 2 ? 2 : 3));
    }
    setup(); put32(records[1] + 16, 2); record_crc(records[1]);
    run(); CHECK(!r->status && r->config_generation == 2 && guards());
    setup(); put32(records[3] + 16, 3); record_crc(records[3]);
    run(); CHECK(!r->status && r->state_generation == 3 && guards());
    setup(); records[1][38] ^= 1; record_crc(records[1]); BLOCK(RB_BTARGET_CONFIG);
    CHECK(r->detail == RB_CONFIG_CONFLICT && !r->error_lba);
    setup(); records[3][48] ^= 1; record_crc(records[3]); BLOCK(RB_BTARGET_STATE);
    CHECK(r->detail == RB_CONFIG_CONFLICT && !r->error_lba);
    /* Legacy configurations have no media identity, even when valid. */
    setup();
    for (i = 0; i < 2; ++i) {
        put16(records[i] + 8, 1);
        for (j = 48; j < 508; ++j) { records[i][j] = 0; }
        put16(records[i] + 36, 0); put32(records[i] + 40, 0); record_crc(records[i]);
    }
    BLOCK(RB_BTARGET_IDENTITY); CHECK(r->detail == 2);

    faults[0] = 1; faults[1] = 2; faults[2] = 3; faults[3] = 4; faults[4] = 5;
    faults[5] = 7; faults[6] = pass - 5; faults[7] = pass - 4; faults[8] = pass - 3;
    faults[9] = pass - 2; faults[10] = pass - 1; faults[11] = pass;
    faults[12] = pass + 1; faults[13] = pass + 2; faults[14] = total - 5;
    faults[15] = total - 4; faults[16] = total - 3; faults[17] = total - 2;
    faults[18] = total - 1; faults[19] = total;
    for (i = 0; i < 20; ++i) {
        setup(); io_call = faults[i]; run();
        CHECK((r->status == RB_BTARGET_IO || r->status == RB_BTARGET_ALLOCATION) && cleared());
        CHECK(reads == io_call && r->error_lba == requested[reads - 1]);
    }
    for (i = 1; i <= 6; ++i) {
        setup(); change_pass = i; BLOCK(RB_BTARGET_CHANGED); CHECK(reads == total);
    }
    setup(); run(); CHECK(!r->status); reads = 0; io_call = 1;
    BLOCK(RB_BTARGET_IO); CHECK(reads == 1);
    setup(); run(); CHECK(!r->status && guards());
    return report(n, 0);
}
