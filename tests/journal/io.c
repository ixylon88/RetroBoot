#include "journal_io.h"
#include "journal_io_fixture.h"

static rb_u8 mbr[512], ebr[512], vbr[512], root[1024];
static rb_journal_diagnosis result;
static rb_u8 journals[2][1536], records[4][512];
static rb_u16 changing_mbr, payload_reads, final_io;
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
    if (!lba && mbr_reads && final_io) { return 1; }
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
    } else {
        for (i = 0; i < 4; ++i) {
            if (lba == 3209UL + i * 100UL) { source = records[i]; ++payload_reads; }
        }
        for (i = 0; i < 6; ++i) {
            if (lba == 3609UL + (i / 3) * 100UL + (i % 3) * 2UL) {
                source = journals[i / 3] + (i % 3) * 512; ++payload_reads;
            }
        }
        if (!source) { ++unexpected; return 1; }
    }
    if (source) { for (i = 0; i < 512; ++i) { data[i] = source[i]; } }
    if (!lba && mbr_reads > 1 && changing_mbr) { data[100] ^= 1; }
    return 0;
}
static void setup(void)
{
    rb_u16 i;
    reads = mbr_reads = vbr_reads = fat0_reads = value_count = changing_mbr = payload_reads = final_io = 0;
    mirror = changing = full_root = last_duplicate = unexpected = 0; fault_lba = 0xFFFFFFFFUL;
    for (i = 0; i < 512; ++i) { mbr[i] = ebr[i] = vbr[i] = 0; }
    for (i = 0; i < 1024; ++i) { root[i] = 0; }
    mbr[432] = 'R'; mbr[433] = 'B'; mbr[434] = 'M'; mbr[435] = '1';
    put32(mbr + 436, 126); put32(mbr + 440, 0x52425431UL);
    mbr[498] = 5; put32(mbr + 502, 63); put32(mbr + 506, 5348UL);
    ebr[450] = 0x16; put32(ebr + 454, 63); put32(ebr + 458, 5285UL);
    mbr[510] = ebr[510] = vbr[510] = 0x55; mbr[511] = ebr[511] = vbr[511] = 0xAA;
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
    for (i = 0; i < 1536; ++i) { journals[0][i] = journals[1][i] = rb_io_journal[i]; }
    for (i = 0; i < 512; ++i) {
        mbr[i] = rb_io_journal[512 + i];
        records[0][i] = records[1][i] = rb_io_config[i]; records[2][i] = records[3][i] = rb_io_state[i];
    }
}

static void record_crc(rb_u8 *p) { put32(p + 508, rb_crc32(p, 508)); }
static rb_u16 report(rb_u16 n)
{
    const char digits[] = "0123456789ABCDEF";
    rb_putc('D'); rb_putc('='); rb_putc(digits[n >> 12]); rb_putc(digits[(n >> 8) & 15]);
    rb_putc(digits[(n >> 4) & 15]); rb_putc(digits[n & 15]); rb_putc(13); rb_putc(10); return n;
}
static rb_u16 cleared(void)
{
    rb_u16 i; const rb_u8 *p = (const rb_u8 *)&result.journal.record;
    for (i = 0; i < sizeof(result.journal.record); ++i) { if (p[i]) { return 0; } }
    return result.journal.source == RB_JOURNAL_NONE && !result.journal.observation;
}
#define CHECK(c) do { ++n; if (!(c)) { return report(n); } } while (0)
#define LOAD() rb_journal_load(&result, read_mock, (void *)0, 262144UL, 0, 0x52425431UL, 126, 1, 0, 0)
#define BLOCK(c) do { LOAD(); CHECK(result.status == (c) && cleared() && !unexpected); } while (0)

rb_u16 __cdecl rb_journal_io_selftest(void)
{
    rb_u16 n = 0, i;
    setup(); LOAD(); CHECK(!result.status && !result.journal.status && result.journal.observation == RB_TX_PREPARED_OLD);
    CHECK(payload_reads == 10 && mbr_reads == 2 && !unexpected);
    for (i = 0; i < 512; ++i) { mbr[i] = journals[0][1024 + i]; }
    LOAD(); CHECK(!result.status && result.journal.observation == RB_TX_PREPARED_NEW);
    put16(journals[1] + 36, RB_TX_COMMITTED); record_crc(journals[1]);
    LOAD(); CHECK(!result.status && result.journal.observation == RB_TX_COMMITTED_NEW && result.journal.source == 1);
    setup(); journals[0][700] ^= 1; LOAD();
    CHECK(!result.status && result.journal.status == RB_JOURNAL_DEGRADED && result.journal.copies[0] == RB_JOURNAL_CRC && cleared());
    setup(); put32(journals[1] + 16, 3); record_crc(journals[1]); LOAD();
    CHECK(!result.status && result.journal.status == RB_JOURNAL_CONFLICT && cleared());
    for (i = 0; i < 6; ++i) {
        setup(); fault_lba = 3609UL + (i / 3) * 100UL + (i % 3) * 2UL; BLOCK(RB_JLOAD_IO);
        CHECK(result.error_lba == fault_lba && result.detail == 7 + i / 3 && result.journal.status == RB_JOURNAL_DEGRADED);
    }
    for (i = 0; i < 4; ++i) {
        setup(); fault_lba = 3209UL + i * 100UL; BLOCK(RB_JLOAD_IO); CHECK(result.error_lba == fault_lba);
    }
    setup(); records[0][80] ^= 1; BLOCK(RB_JLOAD_CONFIG); CHECK(result.detail == 4 && payload_reads == 2);
    setup(); records[3][80] ^= 1; BLOCK(RB_JLOAD_STATE); CHECK(result.detail == 4 && payload_reads == 4);
    setup(); records[0][48] ^= 1; put32(records[0]+16,2); record_crc(records[0]); BLOCK(RB_JLOAD_IDENTITY);
    setup(); records[2][48] ^= 1; put32(records[2]+16,2); record_crc(records[2]); BLOCK(RB_JLOAD_IDENTITY);
    setup(); root[800] = 0xE5; BLOCK(RB_JLOAD_ALLOCATION); CHECK(result.detail == 4 && !payload_reads);
    setup(); changing_mbr = 1; BLOCK(RB_JLOAD_CHANGED);
    setup(); LOAD(); CHECK(!result.status); records[0][80] ^= 1; BLOCK(RB_JLOAD_CONFIG);
    setup(); fault_lba = 378; BLOCK(RB_JLOAD_ALLOCATION); CHECK(result.detail == 3 && !payload_reads);
    setup(); rb_journal_load(&result, read_mock, (void *)0, 262144UL, 0, 0x52425431UL, 126, 2, 16, 63);
    CHECK(!result.status && result.journal.status == RB_JOURNAL_UNAVAILABLE && result.journal.copies[0] == RB_JOURNAL_GEOMETRY && cleared());
    setup(); final_io = 1; BLOCK(RB_JLOAD_IO); CHECK(!result.error_lba && !result.detail);
    report(n); return 0;
}
