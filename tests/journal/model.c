#include "journal.h"
#include "journal_fixture.h"

static rb_u8 a[1536], b[1536], current[512];
static rb_partition_scan scan;
static rb_journal_context context;
static rb_journal_result result;
static rb_journal_record decoded;

static void put16(rb_u8 *p, rb_u16 v) { p[0] = (rb_u8)v; p[1] = (rb_u8)(v >> 8); }
static void put32(rb_u8 *p, rb_u32 v) { put16(p, (rb_u16)v); put16(p + 2, (rb_u16)(v >> 16)); }
static void copy(rb_u8 *to, const rb_u8 *from, rb_u16 n)
{
    rb_u16 i; for (i = 0; i < n; ++i) { to[i] = from[i]; }
}
static rb_u16 zero(const void *p, rb_u16 n)
{
    const rb_u8 *bytes = (const rb_u8 *)p;
    while (n) { if (bytes[--n]) { return 0; } } return 1;
}
static void seal(rb_u8 *p)
{
    put32(p + 64, rb_crc32(p + 512, 512)); put32(p + 68, rb_crc32(p + 1024, 512));
    put32(p + 508, rb_crc32(p, 508));
}
static void phase(rb_u8 *p, rb_u32 sequence, rb_u16 value)
{
    put32(p + 16, sequence); put16(p + 36, value); seal(p);
}
static void baseline(rb_u8 *p)
{
    copy(p + 1024, p + 512, 512); phase(p, 1, RB_TX_EMPTY);
}
static void reverse(rb_u8 *p, rb_u32 sequence)
{
    rb_u16 i; rb_u8 byte;
    for (i = 0; i < 512; ++i) { byte = p[512 + i]; p[512 + i] = p[1024 + i]; p[1024 + i] = byte; }
    phase(p, sequence, RB_TX_PREPARED);
}
static void setup(void)
{
    rb_u16 i; rb_u8 *bytes;
    copy(a, rb_journal_vector, 1536); copy(b, a, 1536); copy(current, a + 512, 512);
    bytes = (rb_u8 *)&scan; for (i = 0; i < sizeof(scan); ++i) { bytes[i] = 0; }
    bytes = (rb_u8 *)&context; for (i = 0; i < sizeof(context); ++i) { bytes[i] = 0; }
    scan.disk_id = 0x52425431UL; scan.count = 5; scan.ebr_count = 1; scan.ebr_lba[0] = 63;
    for (i = 0; i < 4; ++i) { scan.entries[i].slot = i + 1; }
    scan.entries[0].type = 6; scan.entries[0].flag = 0x80;
    scan.entries[0].start = 131072UL; scan.entries[0].sectors = 5073;
    scan.entries[1].type = 0x16; scan.entries[1].start = 140000UL; scan.entries[1].sectors = 5073;
    scan.entries[3].type = 5; scan.entries[3].start = 63; scan.entries[3].sectors = 128520UL;
    scan.entries[4].type = 0x16; scan.entries[4].start = 126; scan.entries[4].sectors = 128457UL;
    scan.entries[4].logical = 1; scan.entries[4].slot = 1; scan.entries[4].table_lba = 63;
    context.scan = &scan; context.capacity_low = 262144UL; context.admin_index = 4; context.io_mode = 1;
    copy(context.media_id, a + 48, 16);
}
static rb_u16 report(rb_u16 n)
{
    const char digits[] = "0123456789ABCDEF";
    rb_putc('T'); rb_putc('='); rb_putc(digits[(n >> 12) & 15]); rb_putc(digits[(n >> 8) & 15]);
    rb_putc(digits[(n >> 4) & 15]); rb_putc(digits[n & 15]); rb_putc(13); rb_putc(10); return n;
}
#define CHECK(c) do { ++n; if (!(c)) { return report(n); } } while (0)
#define DECODE() rb_journal_decode(&decoded, a, 1536, &context)
#define REJECT(c) CHECK(DECODE() == (c) && zero(&decoded, sizeof(decoded)))
#define INSPECT() rb_journal_inspect(&result, a, b, 3, &context, current)
#define OBSERVE(c) do { INSPECT(); CHECK(result.status == 0 && result.observation == (c)); } while (0)
#define BLOCK(c) do { INSPECT(); CHECK(result.status == (c) && result.source == RB_JOURNAL_NONE \
    && result.observation == RB_TX_UNOBSERVED && zero(&result.record, sizeof(result.record))); } while (0)

rb_u16 __cdecl rb_journal_selftest(void)
{
    rb_u16 n = 0, i, j, mask;
    rb_u32 hash;
    const rb_u16 corruption[] = {0, 8, 10, 12, 16, 20, 36, 38, 48, 64, 72, 76, 507, 508, 511, 512, 1023, 1024, 1535};
    const rb_u16 protected_bytes[] = {0, 100, 431, 444, 445, 447, 451, 463, 467, 495, 499};
    setup(); CHECK(DECODE() == 0);
    CHECK(decoded.sequence == 2 && decoded.phase == RB_TX_PREPARED && decoded.changed == 3);
    CHECK(decoded.before_crc == 0xDF25514CUL && decoded.after_crc == 0x1E786A6DUL);
    CHECK(rb_layout_crc(&scan) == 0x5AC2C6E5UL && rb_crc32(a, 508) == 0x09E5A5BCUL);
    for (i = 0; i < sizeof(corruption) / sizeof(corruption[0]); ++i) {
        setup(); a[corruption[i]] ^= 1; CHECK(DECODE() != 0 && zero(&decoded, sizeof(decoded)));
    }
    setup(); CHECK(rb_journal_decode(&decoded, (const rb_u8 *)0, 0, &context) == RB_JOURNAL_FORMAT);
    CHECK(rb_journal_decode(&decoded, a, 1535, &context) == RB_JOURNAL_FORMAT);
    CHECK(rb_journal_decode(&decoded, a, 1537, &context) == RB_JOURNAL_FORMAT);
    setup(); a[8] = 2; seal(a); REJECT(RB_JOURNAL_FORMAT);
    setup(); a[76] = 1; seal(a); REJECT(RB_JOURNAL_FORMAT);
    setup(); phase(a, 0, RB_TX_PREPARED); REJECT(RB_JOURNAL_FORMAT);
    setup(); phase(a, 1, RB_TX_PREPARED); REJECT(RB_JOURNAL_FORMAT);
    setup(); phase(a, 2, RB_TX_EMPTY); REJECT(RB_JOURNAL_FORMAT);
    setup(); phase(a, 2, 3); REJECT(RB_JOURNAL_FORMAT);
    setup(); for (i = 48; i < 64; ++i) { a[i] = 0; } seal(a); REJECT(RB_JOURNAL_FORMAT);
    setup(); a[20] ^= 1; seal(a); REJECT(RB_JOURNAL_IDENTITY);
    setup(); a[24] ^= 1; seal(a); REJECT(RB_JOURNAL_IDENTITY);
    setup(); a[28] ^= 1; seal(a); REJECT(RB_JOURNAL_IDENTITY);
    setup(); a[32] ^= 1; seal(a); REJECT(RB_JOURNAL_IDENTITY);
    setup(); a[48] ^= 1; seal(a); REJECT(RB_JOURNAL_IDENTITY);
    setup(); scan.status = RB_SCAN_IO; REJECT(RB_JOURNAL_IDENTITY);
    setup(); context.admin_index = 3; REJECT(RB_JOURNAL_IDENTITY);
    setup(); context.admin_index = 5; REJECT(RB_JOURNAL_IDENTITY);
    setup(); scan.count = 21; REJECT(RB_JOURNAL_IDENTITY);
    setup(); scan.ebr_count = 17; REJECT(RB_JOURNAL_IDENTITY);
    setup(); scan.entries[4].type = 6; REJECT(RB_JOURNAL_IDENTITY);
    setup(); context.media_id[0] ^= 1; REJECT(RB_JOURNAL_IDENTITY);
    setup(); a[40] ^= 1; seal(a); REJECT(RB_JOURNAL_GEOMETRY);
    setup(); a[44] = 1; seal(a); REJECT(RB_JOURNAL_GEOMETRY);
    setup(); a[72] = 16; seal(a); REJECT(RB_JOURNAL_GEOMETRY);
    setup(); context.io_mode = 3; REJECT(RB_JOURNAL_GEOMETRY);
    setup(); context.heads = 16; REJECT(RB_JOURNAL_GEOMETRY);
    setup(); context.capacity_high = 1; put32(a + 44, 1); seal(a); CHECK(DECODE() == 0);
    setup(); context.io_mode = 2; context.heads = 16; context.sectors_per_track = 63;
    context.capacity_low = 1032192UL; put16(a + 38, 2); put32(a + 40, context.capacity_low);
    put16(a + 72, 16); put16(a + 74, 63); seal(a); CHECK(DECODE() == 0);
    context.heads = 17; REJECT(RB_JOURNAL_GEOMETRY);
    context.heads = 0; REJECT(RB_JOURNAL_GEOMETRY);
    context.heads = 257; REJECT(RB_JOURNAL_GEOMETRY);
    context.heads = 16; context.sectors_per_track = 64; REJECT(RB_JOURNAL_GEOMETRY);
    context.sectors_per_track = 63; context.capacity_low = 1032193UL; put32(a + 40, context.capacity_low); seal(a);
    REJECT(RB_JOURNAL_GEOMETRY);
    setup(); a[512 + 510] = 0; seal(a); REJECT(RB_JOURNAL_MBR);
    setup(); a[1024 + 511] = 0; seal(a); REJECT(RB_JOURNAL_MBR);
    setup(); a[512 + 440] ^= 1; seal(a); REJECT(RB_JOURNAL_MBR);
    setup(); a[512 + 436] ^= 1; seal(a); REJECT(RB_JOURNAL_MBR);
    setup(); a[1024 + 432] = 'X'; seal(a); REJECT(RB_JOURNAL_MBR);
    setup(); a[1024 + 454] ^= 1; seal(a); REJECT(RB_JOURNAL_MBR);
    setup(); a[1024 + 466] = 7; seal(a); REJECT(RB_JOURNAL_MBR);
    setup(); a[1024 + 478] = 1; seal(a); REJECT(RB_JOURNAL_MBR);
    setup(); a[1024 + 494] = 0x80; seal(a); REJECT(RB_JOURNAL_MBR);
    setup(); a[1024 + 446] = 0x80; seal(a); REJECT(RB_JOURNAL_MBR);
    setup(); a[1024 + 462] = 0; seal(a); REJECT(RB_JOURNAL_MBR);
    setup(); a[1024 + 466] = 0x16; seal(a); REJECT(RB_JOURNAL_MBR);
    for (i = 0; i < sizeof(protected_bytes) / sizeof(protected_bytes[0]); ++i) {
        setup(); a[1024 + protected_bytes[i]] ^= 1; seal(a); REJECT(RB_JOURNAL_DELTA);
    }
    setup(); copy(a + 1024, a + 512, 512); seal(a); REJECT(RB_JOURNAL_DELTA);
    setup(); phase(a, 1, RB_TX_EMPTY); REJECT(RB_JOURNAL_DELTA);
    setup(); a[1024 + 450] = 6; seal(a); CHECK(DECODE() == 0 && decoded.changed == 3); /* NT-style group */

    setup(); baseline(a); copy(b, a, 1536); OBSERVE(RB_TX_BASELINE);
    current[100] ^= 1; OBSERVE(RB_TX_DIVERGED);
    setup(); baseline(b); hash = rb_crc32(a, 1536); OBSERVE(RB_TX_PREPARED_OLD);
    CHECK(result.source == 0 && rb_crc32(a, 1536) == hash);
    copy(current, a + 1024, 512); OBSERVE(RB_TX_PREPARED_NEW);
    current[0] ^= 1; OBSERVE(RB_TX_DIVERGED);
    setup(); baseline(a); OBSERVE(RB_TX_PREPARED_OLD); CHECK(result.source == 1);
    setup(); phase(b, 2, RB_TX_COMMITTED); copy(current, b + 1024, 512); OBSERVE(RB_TX_COMMITTED_NEW);
    CHECK(result.source == 1 && result.record.phase == RB_TX_COMMITTED);
    copy(current, a + 512, 512); OBSERVE(RB_TX_DIVERGED);
    setup(); phase(a, 2, RB_TX_COMMITTED); copy(current, a + 1024, 512); OBSERVE(RB_TX_COMMITTED_NEW);
    CHECK(result.source == 0);
    setup(); OBSERVE(RB_TX_PREPARED_OLD); copy(current, a + 1024, 512); OBSERVE(RB_TX_PREPARED_NEW);
    setup(); phase(a, 2, RB_TX_COMMITTED); copy(b, a, 1536); copy(current, a + 1024, 512); OBSERVE(RB_TX_COMMITTED_NEW);
    reverse(a, 3); OBSERVE(RB_TX_PREPARED_OLD); copy(current, a + 1024, 512); OBSERVE(RB_TX_PREPARED_NEW);
    copy(b, a, 1536); phase(b, 3, RB_TX_COMMITTED); OBSERVE(RB_TX_COMMITTED_NEW);

    setup(); phase(b, 3, RB_TX_PREPARED); BLOCK(RB_JOURNAL_CONFLICT); /* two pending transactions */
    setup(); baseline(b); phase(a, 3, RB_TX_PREPARED); BLOCK(RB_JOURNAL_CONFLICT); /* skipped sequence */
    setup(); phase(b, 2, RB_TX_COMMITTED); phase(a, 3, RB_TX_PREPARED); BLOCK(RB_JOURNAL_CONFLICT); /* broken predecessor */
    setup(); phase(a, 3, RB_TX_COMMITTED); BLOCK(RB_JOURNAL_CONFLICT); /* completion without its prepare */
    setup(); b[512 + 100] ^= 1; b[1024 + 100] ^= 1; seal(b); BLOCK(RB_JOURNAL_CONFLICT);
    setup(); b[512 + 100] ^= 1; b[1024 + 100] ^= 1; phase(b, 2, RB_TX_COMMITTED); BLOCK(RB_JOURNAL_CONFLICT);
    setup(); phase(a, 0xFFFFFFFFUL, RB_TX_PREPARED); phase(b, 0xFFFFFFFFUL, RB_TX_COMMITTED);
    copy(current, a + 1024, 512); OBSERVE(RB_TX_COMMITTED_NEW);
    baseline(a); BLOCK(RB_JOURNAL_CONFLICT); /* no wrap or implicit reset */

    /* Torn replacement of each subset of the three sectors cannot select an
     * older completion as if it proved the new transaction. */
    for (mask = 1; mask < 7; ++mask) {
        setup(); phase(b, 2, RB_TX_COMMITTED); reverse(a, 3);
        for (i = 0; i < 3; ++i) {
            if (mask & (1U << i)) { for (j = 0; j < 512; ++j) { a[i * 512 + j] = b[i * 512 + j]; } }
        }
        BLOCK(RB_JOURNAL_DEGRADED);
    }
    setup(); baseline(b); a[700] ^= 1; BLOCK(RB_JOURNAL_DEGRADED); CHECK(result.copies[0] == RB_JOURNAL_CRC);
    setup(); phase(b, 2, RB_TX_COMMITTED); b[1200] ^= 1; BLOCK(RB_JOURNAL_DEGRADED);
    setup(); a[700] ^= 1; b[1200] ^= 1; BLOCK(RB_JOURNAL_UNAVAILABLE);
    setup(); OBSERVE(RB_TX_PREPARED_OLD); a[700] ^= 1; BLOCK(RB_JOURNAL_DEGRADED); /* clear prior success */
    setup(); rb_journal_inspect(&result, a, (const rb_u8 *)0, 1, &context, current);
    CHECK(result.status == RB_JOURNAL_DEGRADED && result.copies[1] == RB_JOURNAL_MISSING && result.source == RB_JOURNAL_NONE);
    rb_journal_inspect(&result, (const rb_u8 *)0, b, 2, &context, current);
    CHECK(result.status == RB_JOURNAL_DEGRADED && result.copies[0] == RB_JOURNAL_MISSING);
    rb_journal_inspect(&result, (const rb_u8 *)0, (const rb_u8 *)0, 0, &context, (const rb_u8 *)0);
    CHECK(result.status == RB_JOURNAL_UNAVAILABLE && result.copies[0] == RB_JOURNAL_MISSING && result.copies[1] == RB_JOURNAL_MISSING);
    rb_journal_inspect(&result, a, b, 4, &context, current); CHECK(result.status == RB_JOURNAL_UNAVAILABLE);
    report(n); return 0;
}
