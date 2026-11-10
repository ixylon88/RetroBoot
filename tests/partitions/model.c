#include "partitions.h"

typedef struct {
    rb_u8 blocks[4][512];
    rb_u32 locations[4], reads[20], fail_lba;
    rb_u16 read_count;
} mock_disk;

static void put32(rb_u8 *p, rb_u32 value)
{
    rb_u16 i;
    for (i = 0; i < 4; ++i) { p[i] = (rb_u8)value; value >>= 8; }
}

static void entry(rb_u8 *block, rb_u16 slot, rb_u16 type,
                  rb_u32 start, rb_u32 count, rb_u16 flag)
{
    rb_u16 i;
    rb_u8 *p = block + 446 + slot * 16;
    for (i = 0; i < 16; ++i) { p[i] = 0; }
    p[0] = (rb_u8)flag; p[4] = (rb_u8)type;
    put32(p + 8, start); put32(p + 12, count);
}

static void setup(mock_disk *disk)
{
    rb_u16 i;
    rb_u8 *bytes = (rb_u8 *)disk;
    for (i = 0; i < sizeof(*disk); ++i) { bytes[i] = 0; }
    for (i = 0; i < 4; ++i) { disk->blocks[i][510] = 0x55; disk->blocks[i][511] = 0xAA; }
    disk->locations[1] = 100; disk->locations[2] = 200; disk->locations[3] = 400;
    disk->fail_lba = 0xFFFFFFFFUL;
    put32(disk->blocks[0] + 440, 0x52425431UL);
    entry(disk->blocks[0], 0, 0x06, 10, 20, 0x80);
    entry(disk->blocks[0], 3, 0x05, 100, 1000, 0);
    entry(disk->blocks[1], 0, 0x06, 1, 50, 0);
    entry(disk->blocks[1], 1, 0x05, 100, 900, 0);
    entry(disk->blocks[2], 0, 0x16, 1, 50, 0);
}

static void reverse_chain(mock_disk *disk)
{
    setup(disk);
    disk->locations[2] = 400; disk->locations[3] = 200;
    entry(disk->blocks[1], 1, 0x05, 300, 700, 0);
    entry(disk->blocks[2], 1, 0x05, 100, 900, 0);
    entry(disk->blocks[3], 0, 0x0B, 1, 50, 0);
}

static rb_u16 __cdecl read_mock(rb_u32 lba, rb_u8 *sector, void *opaque)
{
    mock_disk *disk = (mock_disk *)opaque;
    rb_u16 i, j;
    if (disk->read_count >= 20) { return 1; }
    disk->reads[disk->read_count++] = lba;
    if (lba == disk->fail_lba) { return 1; }
    for (i = 0; i < 4; ++i) {
        if (disk->locations[i] == lba) {
            for (j = 0; j < 512; ++j) { sector[j] = disk->blocks[i][j]; }
            return 0;
        }
    }
    return 1;
}

#define CHECK(condition) do { ++number; if (!(condition)) { return number; } } while (0)
#define EXPECT(code, lba, slot) CHECK(rb_scan_partitions(&r, read_mock, &disk, 2000, 0, 0x52425431UL) == (code) && r.error_lba == (lba) && r.error_slot == (slot))

/* The real C/16 parser and callback ABI, not a host-language reimplementation. */
rb_u16 __cdecl rb_scan_selftest(void)
{
    mock_disk disk;
    rb_partition_scan r;
    rb_u16 number = 0;
    setup(&disk);
    EXPECT(RB_SCAN_OK, 0, 0);
    CHECK(r.count == 6 && r.ebr_count == 2 && r.entries[4].start == 101
          && r.entries[5].start == 201 && r.entries[5].type == 0x16
          && disk.read_count == 3 && disk.reads[2] == 200);
    reverse_chain(&disk);
    EXPECT(RB_SCAN_OK, 0, 0);
    CHECK(r.count == 7 && r.entries[5].start == 401 && r.entries[6].start == 201
          && disk.reads[2] == 400 && disk.reads[3] == 200);
    setup(&disk); entry(disk.blocks[0], 3, 0, 0, 0, 0);
    EXPECT(RB_SCAN_OK, 0, 0);
    CHECK(r.count == 4 && disk.read_count == 1);
    setup(&disk); entry(disk.blocks[1], 0, 0, 0, 0, 0); entry(disk.blocks[1], 1, 0, 0, 0, 0);
    EXPECT(RB_SCAN_OK, 0, 0);
    CHECK(r.count == 4 && r.ebr_count == 1);
    setup(&disk); disk.blocks[0][510] = 0;
    EXPECT(RB_SCAN_SIGNATURE, 0, 0);
    setup(&disk); disk.blocks[0][440] ^= 1;
    EXPECT(RB_SCAN_IDENTITY, 0, 0);
    setup(&disk); disk.fail_lba = 0;
    EXPECT(RB_SCAN_IO, 0, 0);
    setup(&disk); disk.fail_lba = 100;
    EXPECT(RB_SCAN_IO, 100, 0);
    setup(&disk); disk.blocks[2][511] = 0;
    EXPECT(RB_SCAN_SIGNATURE, 200, 0);
    setup(&disk); disk.blocks[0][446] = 1;
    EXPECT(RB_SCAN_FLAGS, 0, 1);
    setup(&disk); entry(disk.blocks[0], 1, 0x07, 40, 10, 0x80);
    EXPECT(RB_SCAN_FLAGS, 0, 2);
    setup(&disk); disk.blocks[0][494] = 0x80;
    EXPECT(RB_SCAN_FLAGS, 0, 4);
    setup(&disk); disk.blocks[1][446] = 0x80;
    EXPECT(RB_SCAN_FLAGS, 100, 1);
    setup(&disk); disk.blocks[1][462] = 0x80;
    EXPECT(RB_SCAN_FLAGS, 100, 2);
    setup(&disk); disk.blocks[0][450] = 0x83;
    EXPECT(RB_SCAN_TYPE, 0, 1);
    setup(&disk); disk.blocks[0][450] = 0xEE;
    EXPECT(RB_SCAN_TYPE, 0, 1);
    setup(&disk); entry(disk.blocks[0], 1, 0, 1, 1, 0);
    EXPECT(RB_SCAN_EMPTY, 0, 2);
    setup(&disk); entry(disk.blocks[0], 0, 0x06, 0, 20, 0);
    EXPECT(RB_SCAN_RANGE, 0, 1);
    setup(&disk); entry(disk.blocks[0], 0, 0x06, 10, 0, 0);
    EXPECT(RB_SCAN_RANGE, 0, 1);
    setup(&disk); entry(disk.blocks[0], 0, 0x06, 0xFFFFFFF0UL, 32, 0);
    EXPECT(RB_SCAN_OVERFLOW, 0, 1);
    setup(&disk); entry(disk.blocks[0], 3, 0, 0, 0, 0);
    entry(disk.blocks[0], 0, 0x06, 0xFFFFFFFFUL, 1, 0);
    CHECK(rb_scan_partitions(&r, read_mock, &disk, 0, 1, 0x52425431UL) == RB_SCAN_OK);
    CHECK(rb_scan_partitions(&r, read_mock, &disk, 0xFFFFFFFFUL, 0, 0x52425431UL) == RB_SCAN_RANGE);
    setup(&disk); entry(disk.blocks[0], 1, 0x07, 30, 20, 0);
    EXPECT(RB_SCAN_OK, 0, 0);
    setup(&disk); entry(disk.blocks[0], 1, 0x07, 29, 1, 0);
    EXPECT(RB_SCAN_OVERLAP, 0, 2);
    setup(&disk);
    CHECK(rb_scan_partitions(&r, read_mock, &disk, 0, 0, 0x52425431UL) == RB_SCAN_RANGE && disk.read_count == 0);
    setup(&disk); entry(disk.blocks[0], 3, 0x05, 100, 1901, 0);
    EXPECT(RB_SCAN_RANGE, 0, 4);
    setup(&disk); entry(disk.blocks[0], 1, 0x05, 40, 10, 0);
    EXPECT(RB_SCAN_EXTENDED, 0, 4);
    setup(&disk); entry(disk.blocks[1], 0, 0x06, 0xFFFFFFFFUL, 1, 0);
    EXPECT(RB_SCAN_OVERFLOW, 100, 1);
    setup(&disk); entry(disk.blocks[1], 0, 0x06, 0, 1, 0);
    EXPECT(RB_SCAN_RANGE, 100, 1);
    setup(&disk); entry(disk.blocks[1], 0, 0x06, 1, 1000, 0);
    EXPECT(RB_SCAN_RANGE, 100, 1);
    setup(&disk); entry(disk.blocks[1], 0, 0x06, 200, 50, 0);
    entry(disk.blocks[2], 0, 0x16, 101, 50, 0);
    EXPECT(RB_SCAN_OVERLAP, 200, 1);
    setup(&disk); entry(disk.blocks[1], 1, 0x05, 20, 980, 0);
    EXPECT(RB_SCAN_OVERLAP, 120, 0);
    CHECK(disk.read_count == 2);
    reverse_chain(&disk); entry(disk.blocks[3], 0, 0x06, 100, 101, 0);
    EXPECT(RB_SCAN_OVERLAP, 200, 1);
    setup(&disk); entry(disk.blocks[1], 1, 0x05, 0, 1000, 0);
    EXPECT(RB_SCAN_LOOP, 100, 0);
    CHECK(disk.read_count == 2);
    setup(&disk); entry(disk.blocks[2], 1, 0x05, 0, 1000, 0);
    EXPECT(RB_SCAN_LOOP, 100, 0);
    CHECK(disk.read_count == 3);
    setup(&disk); entry(disk.blocks[1], 1, 0, 1, 0, 0);
    EXPECT(RB_SCAN_EMPTY, 100, 2);
    setup(&disk); disk.blocks[1][466] = 0x06;
    EXPECT(RB_SCAN_TYPE, 100, 2);
    setup(&disk); entry(disk.blocks[1], 2, 0x06, 1, 1, 0);
    EXPECT(RB_SCAN_SLOTS, 100, 3);
    setup(&disk); entry(disk.blocks[1], 3, 0x06, 1, 1, 0);
    EXPECT(RB_SCAN_SLOTS, 100, 4);
    setup(&disk); disk.blocks[1][450] = 0x05;
    EXPECT(RB_SCAN_TYPE, 100, 1);
    setup(&disk); entry(disk.blocks[1], 1, 0x05, 0xFFFFFFFFUL, 1, 0);
    EXPECT(RB_SCAN_OVERFLOW, 100, 2);
    setup(&disk); entry(disk.blocks[1], 1, 0x05, 100, 0, 0);
    EXPECT(RB_SCAN_RANGE, 100, 2);
    setup(&disk); entry(disk.blocks[1], 1, 0x05, 2000, 1, 0);
    EXPECT(RB_SCAN_RANGE, 100, 2);
    setup(&disk); entry(disk.blocks[1], 0, 0, 1, 0, 0);
    EXPECT(RB_SCAN_EMPTY, 100, 1);
    return 0;
}
