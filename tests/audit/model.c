#include "admin_audit.h"

static rb_u8 mbr[512], ebr[512], vbr[512], root[1024];
static rb_admin_audit result;
static struct { rb_u16 cluster, value; } values[132];
static rb_u16 value_count, reads, mbr_reads, vbr_reads, fat0_reads;
static rb_u16 mirror, changing, full_root, last_duplicate, unexpected;
static rb_u32 fault_lba;

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
    (void)opaque;
    ++reads;
    if (lba == fault_lba) { return 1; }
    for (i = 0; i < 512; ++i) { data[i] = 0; }
    if (!lba) { source = mbr; ++mbr_reads; }
    else if (lba == 63) { source = ebr; }
    else if (lba == 126) { source = vbr; ++vbr_reads; }
    else if (lba >= 379 && lba <= 410) {
        if (lba < 381) { source = root + (rb_u16)(lba - 379) * 512; }
        else if (full_root) { for (i = 0; i < 16; ++i) { data[i * 32] = 0xE5; } }
        if (last_duplicate && lba == 410) {
            for (i = 0; i < 32; ++i) { data[480 + i] = root[672 + i]; }
        }
    } else if (lba >= 127 && lba < 379) {
        copy = lba >= 253; index = (rb_u16)(lba - (copy ? 253 : 127));
        if (!copy && !index) { ++fat0_reads; }
        if (!index) { put16(data, 0xFFF8); put16(data + 2, 0xFFFF); }
        for (i = 0; i < value_count; ++i) {
            if (values[i].cluster / 256 == index) { put16(data + (values[i].cluster % 256) * 2, values[i].value); }
        }
        if (mirror && copy && index == 125) { data[511] ^= 1; }
        if (changing && !index && fat0_reads >= 2) { put16(data + 40, 0xFFFF); }
    } else { ++unexpected; return 1; }
    if (source) { for (i = 0; i < 512; ++i) { data[i] = source[i]; } }
    if (!lba && mbr_reads > 1) { data[510] = 0; }
    return 0;
}
static void setup(void)
{
    rb_u16 i;
    reads = mbr_reads = vbr_reads = fat0_reads = value_count = 0;
    mirror = changing = full_root = last_duplicate = unexpected = 0; fault_lba = 0xFFFFFFFFUL;
    for (i = 0; i < 512; ++i) { mbr[i] = ebr[i] = vbr[i] = 0; }
    for (i = 0; i < 1024; ++i) { root[i] = 0; }
    mbr[432] = 'R'; mbr[433] = 'B'; mbr[434] = 'M'; mbr[435] = '1';
    put32(mbr + 436, 126); put32(mbr + 440, 0x52425431UL);
    mbr[498] = 5; put32(mbr + 502, 63); put32(mbr + 506, 128520UL);
    ebr[450] = 0x16; put32(ebr + 454, 63); put32(ebr + 458, 128457UL);
    mbr[510] = ebr[510] = vbr[510] = 0x55; mbr[511] = ebr[511] = vbr[511] = 0xAA;
    vbr[0] = 0xEB; vbr[2] = 0x90; put16(vbr + 11, 512); vbr[13] = 4;
    put16(vbr + 14, 1); vbr[16] = 2; put16(vbr + 17, 512); vbr[21] = 0xF8;
    put16(vbr + 22, 126); put32(vbr + 28, 126); put32(vbr + 32, 128457UL);
    vbr[62] = 'R'; vbr[63] = 'B'; vbr[64] = 'V'; vbr[65] = '1';
    put32(vbr + 66, 411); put16(vbr + 70, 3); seal();
    entry(0, "RBBOOT  SYS", 2, 1536);
    for (i = 1; i < 20; ++i) { root[i * 32] = 0xE5; }
    entry(20, "RBSTG2  BIN", 20, 5000);
    entry(21, "RBCFG   A  ", 2800, 512); entry(22, "RBCFG   B  ", 2900, 512);
    entry(23, "RBSTATE A  ", 3000, 512); entry(24, "RBSTATE B  ", 3100, 512);
    fat(2, 0xFFFF); fat(20, 30); fat(30, 40); fat(40, 0xFFFF);
    fat(2800, 0xFFFF); fat(2900, 0xFFFF); fat(3000, 0xFFFF); fat(3100, 0xFFFF);
}
static rb_u16 cleared(void)
{
    rb_u16 i;
    const rb_u8 *p = (const rb_u8 *)result.files;
    if (result.total_clusters || result.used_clusters || result.free_clusters) { return 0; }
    for (i = 0; i < sizeof(result.files); ++i) { if (p[i]) { return 0; } }
    return 1;
}
static rb_u16 report(rb_u16 n)
{
    const char digits[] = "0123456789ABCDEF";
    rb_putc('A'); rb_putc('='); rb_putc(digits[(n >> 12) & 15]); rb_putc(digits[(n >> 8) & 15]);
    rb_putc(digits[(n >> 4) & 15]); rb_putc(digits[n & 15]); rb_putc(13); rb_putc(10);
    return n;
}
#define CHECK(c) do { ++n; if (!(c)) { return report(n); } } while (0)
#define AUDIT() rb_audit_admin(&result, read_mock, (void *)0, 262144UL, 0, 0x52425431UL, 126)
#define REJECT(code) CHECK(AUDIT() == (code) && result.status == (code) && cleared() && !unexpected)

rb_u16 __cdecl rb_audit_selftest(void)
{
    rb_u16 n = 0, i;
    setup(); CHECK(AUDIT() == 0);
    CHECK(result.total_clusters == 32043 && result.used_clusters == 8 && result.free_clusters == 32035);
    CHECK(result.files[1].bytes == 5000 && result.files[1].clusters == 3 && result.files[1].first_lba == 483);
    CHECK(reads == 265 && mbr_reads == 1 && vbr_reads == 1 && !unexpected);
    setup(); ebr[450] = 0x1E; CHECK(AUDIT() == 0);
    setup(); entry(1, "RETROBOOT  ", 0, 0); root[43] = 8; CHECK(AUDIT() == 0);
    setup(); root[683] = 0x27; CHECK(AUDIT() == 0);
    setup(); full_root = 1; for (i = 25; i < 32; ++i) { root[i * 32] = 0xE5; }
    CHECK(AUDIT() == 0 && reads == 295);
    setup(); full_root = last_duplicate = 1;
    for (i = 25; i < 32; ++i) { root[i * 32] = 0xE5; }
    REJECT(RB_AUDIT_ROOT); CHECK(result.detail == 2 && result.error_lba == 410);
    setup(); mbr[510] = 0; REJECT(RB_AUDIT_SCAN); CHECK(reads == 1);
    setup(); mbr[436] ^= 1; REJECT(RB_AUDIT_ADMIN); CHECK(!vbr_reads);
    setup(); ebr[450] = 6; REJECT(RB_AUDIT_ADMIN); CHECK(!vbr_reads);
    setup(); vbr[13] = 3; seal(); REJECT(RB_AUDIT_ADMIN); CHECK(result.detail == RB_VOLUME_CLUSTER);
    setup(); vbr[100] ^= 1; REJECT(RB_AUDIT_ADMIN);
    setup(); vbr[64] = 'X'; seal(); REJECT(RB_AUDIT_ADMIN);
    setup(); put16(vbr + 22, 257); seal(); REJECT(RB_AUDIT_ADMIN);
    setup(); entry(25, "UNKNOWN BIN", 4000, 512); REJECT(RB_AUDIT_ROOT); CHECK(result.detail == 1);
    setup(); root[651] = 0x10; REJECT(RB_AUDIT_ROOT); CHECK(result.detail == 4);
    setup(); root[651] = 0x0F; REJECT(RB_AUDIT_ROOT);
    setup(); put16(root + 660, 1); REJECT(RB_AUDIT_ROOT);
    setup(); entry(25, "RBCFG   A  ", 4000, 512); REJECT(RB_AUDIT_ROOT); CHECK(result.detail == 2);
    setup(); root[768] = 0xE5; REJECT(RB_AUDIT_ROOT); CHECK(result.detail == 3 && result.error_file == 6);
    setup(); put32(root + 700, 513); REJECT(RB_AUDIT_ROOT); CHECK(result.detail == 5);
    setup(); put32(root + 668, 49153UL); REJECT(RB_AUDIT_ROOT);
    setup(); put32(root + 28, 1535); REJECT(RB_AUDIT_ROOT);
    setup(); put16(root + 698, 1); REJECT(RB_AUDIT_ROOT); CHECK(result.detail == 6);
    setup(); put16(root + 698, 32045); REJECT(RB_AUDIT_ROOT);
    setup(); put16(root + 730, 2800); REJECT(RB_AUDIT_SHARED); CHECK(result.error_file == 4 && result.detail == 3);
    setup(); put16(root + 698, 30); REJECT(RB_AUDIT_SHARED); CHECK(result.error_cluster == 30 && result.detail == 2);
    setup(); fat(2800, 0); REJECT(RB_AUDIT_CHAIN);
    setup(); fat(2800, 0xFFF7); REJECT(RB_AUDIT_CHAIN);
    setup(); fat(2800, 4000); REJECT(RB_AUDIT_CHAIN);
    setup(); fat(20, 0xFFFF); REJECT(RB_AUDIT_CHAIN);
    setup(); fat(20, 0xFFF0); REJECT(RB_AUDIT_CHAIN);
    setup(); fat(20, 32045); REJECT(RB_AUDIT_CHAIN);
    setup(); fat(30, 20); REJECT(RB_AUDIT_CHAIN); CHECK(result.error_cluster == 20);
    setup(); mirror = 1; REJECT(RB_AUDIT_COPIES); CHECK(result.error_lba == 378);
    setup(); fat(0, 0xFFF0); REJECT(RB_AUDIT_HEADER);
    setup(); fat(1, 0x7FFF); REJECT(RB_AUDIT_HEADER);
    setup(); fat(4000, 0xFFFF); REJECT(RB_AUDIT_ORPHAN); CHECK(result.error_cluster == 4000);
    setup(); fat(4000, 0xFFF7); REJECT(RB_AUDIT_ORPHAN);
    setup(); changing = 1; REJECT(RB_AUDIT_CHANGED); CHECK(result.error_cluster == 20 && result.error_file == 2);
    setup(); put32(vbr + 66, 415); seal(); REJECT(RB_AUDIT_BOOTSTRAP);
    setup(); put16(vbr + 70, 4); seal(); REJECT(RB_AUDIT_BOOTSTRAP);
    setup(); put32(root + 28, 4096); put16(vbr + 70, 8); seal(); fat(2, 4); fat(4, 0xFFFF);
    REJECT(RB_AUDIT_BOOTSTRAP);
    setup(); fault_lba = 380; REJECT(RB_AUDIT_IO); CHECK(result.error_lba == 380);
    setup(); fault_lba = 253; REJECT(RB_AUDIT_IO); CHECK(result.error_lba == 253);
    setup(); fault_lba = 378; REJECT(RB_AUDIT_IO); CHECK(result.error_lba == 378);
    setup(); CHECK(AUDIT() == 0); mbr_reads = vbr_reads = reads = fat0_reads = 0;
    root[768] = 0xE5; REJECT(RB_AUDIT_ROOT);

    /* Exact maximum: 16 bootstrap, 96 Stage 2 and four record clusters. */
    setup(); vbr[13] = 1; put32(vbr + 32, 5285); put32(ebr + 458, 5285); put32(mbr + 506, 5348);
    put16(vbr + 70, 16); seal(); put32(root + 28, 8192); put32(root + 668, 49152UL);
    value_count = 0;
    for (i = 2; i < 18; ++i) { fat(i, i == 17 ? 0xFFFF : i + 1); }
    for (i = 20; i < 116; ++i) { fat(i, i == 115 ? 0xFFFF : i + 1); }
    fat(2800, 0xFFFF); fat(2900, 0xFFFF); fat(3000, 0xFFFF); fat(3100, 0xFFFF);
    CHECK(AUDIT() == 0 && result.total_clusters == 5000 && result.used_clusters == 116 && result.free_clusters == 4884);
    CHECK(result.files[0].clusters == 16 && result.files[1].clusters == 96);
    report(n); return 0;
}
