#include "volume.h"

typedef struct {
    rb_u8 sector[512];
    rb_u32 lba, last_read;
    rb_u16 reads, io_error;
} mock_volume;

static void put16(rb_u8 *p, rb_u16 value)
{
    p[0] = (rb_u8)value; p[1] = (rb_u8)(value >> 8);
}

static void put32(rb_u8 *p, rb_u32 value)
{
    put16(p, (rb_u16)value); put16(p + 2, (rb_u16)(value >> 16));
}

static void setup(mock_volume *disk, rb_partition *p, rb_u16 bits, rb_u32 clusters)
{
    rb_u16 i, reserved = bits == 16 ? 1 : 32;
    rb_u32 fat = (clusters + 2 + (bits == 16 ? 255UL : 127UL)) / (bits == 16 ? 256UL : 128UL);
    rb_u32 total = reserved + 2 * fat + (bits == 16 ? 32 : 0) + clusters;
    rb_u8 *bytes = (rb_u8 *)disk;
    for (i = 0; i < sizeof(*disk); ++i) { bytes[i] = 0; }
    disk->lba = 100;
    p->start = 100; p->sectors = total; p->table_lba = 0;
    p->type = bits == 16 ? 0x06 : 0x0B; p->flag = 0; p->slot = 1; p->logical = 0;
    disk->sector[0] = 0xEB; disk->sector[1] = bits == 16 ? 60 : 88;
    disk->sector[2] = 0x90;
    disk->sector[510] = 0x55; disk->sector[511] = 0xAA;
    put16(disk->sector + 11, 512); disk->sector[13] = 1;
    put16(disk->sector + 14, reserved); disk->sector[16] = 2;
    put16(disk->sector + 17, bits == 16 ? 512 : 0);
    disk->sector[21] = 0xF8;
    put32(disk->sector + 28, p->start);
    put32(disk->sector + 32, total);
    if (bits == 16) { put16(disk->sector + 22, (rb_u16)fat); }
    else {
        put32(disk->sector + 36, fat); put32(disk->sector + 44, 2);
        put16(disk->sector + 48, 1); put16(disk->sector + 50, 6);
    }
}

static rb_u16 __cdecl read_mock(rb_u32 lba, rb_u8 *sector, void *opaque)
{
    mock_volume *disk = (mock_volume *)opaque;
    rb_u16 i;
    ++disk->reads; disk->last_read = lba;
    if (disk->io_error || lba != disk->lba) { return 1; }
    for (i = 0; i < 512; ++i) { sector[i] = disk->sector[i]; }
    return 0;
}

static rb_u16 cleared(const rb_volume_probe *r)
{
    return r->fat_bits == 0 && r->cluster_bytes == 0 && r->fats == 0
        && r->total_sectors == 0 && r->clusters == 0 && r->data_lba == 0 && r->fat_sectors == 0;
}

static rb_u16 report(rb_u16 number)
{
    const char digits[] = "0123456789ABCDEF";
    rb_putc('V'); rb_putc('=');
    rb_putc(digits[(number >> 8) & 15]); rb_putc(digits[(number >> 4) & 15]);
    rb_putc(digits[number & 15]); rb_putc(13); rb_putc(10);
    return number;
}

#define CHECK(condition) do { ++number; if (!(condition)) { return report(number); } } while (0)
#define EXPECT(code) CHECK(rb_probe_volume(&r, &p, read_mock, &disk, 0, 1) == (code) && r.status == (code) && ((code) == 0 || cleared(&r)))
#define FAT16() setup(&disk, &p, 16, 5000)
#define FAT32() setup(&disk, &p, 32, 70000)

typedef struct { rb_u32 a, b, product, quotient, remainder; } math_case;
static const math_case math_cases[] = {
    { 0x00000000UL, 0x00000001UL, 0x00000000UL, 0x00000000UL, 0x00000000UL },
    { 0x00000001UL, 0x00000001UL, 0x00000001UL, 0x00000001UL, 0x00000000UL },
    { 0xFFFFFFFFUL, 0x00000001UL, 0xFFFFFFFFUL, 0xFFFFFFFFUL, 0x00000000UL },
    { 0xFFFFFFFFUL, 0xFFFFFFFFUL, 0x00000001UL, 0x00000001UL, 0x00000000UL },
    { 0xFFFFFFFFUL, 0x00010000UL, 0xFFFF0000UL, 0x0000FFFFUL, 0x0000FFFFUL },
    { 0x80000000UL, 0x00010001UL, 0x80000000UL, 0x00007FFFUL, 0x00008001UL },
    { 0x12345678UL, 0x00009ABCUL, 0xDA73B020UL, 0x00001E1EUL, 0x00002C70UL },
    { 0x00000011UL, 0x00010001UL, 0x00110011UL, 0x00000000UL, 0x00000011UL },
    { 0xFFFFFFFEUL, 0x000000FFUL, 0xFFFFFE02UL, 0x01010100UL, 0x000000FEUL },
    { 0x80000001UL, 0x7FFFFFFFUL, 0xFFFFFFFFUL, 0x00000001UL, 0x00000002UL },
};

/* Executes the production parser in C/16, including overflow and cutovers. */
rb_u16 __cdecl rb_volume_selftest(void)
{
    mock_volume disk;
    rb_partition p;
    rb_volume_probe r;
    rb_u16 number = 0, i;
    volatile rb_u32 a, b;
    const rb_u16 types[] = {0x06, 0x16, 0x0E, 0x1E, 0x0B, 0x1B, 0x0C, 0x1C};
    for (i = 0; i < sizeof(math_cases) / sizeof(math_cases[0]); ++i) {
        a = math_cases[i].a; b = math_cases[i].b;
        CHECK(a * b == math_cases[i].product);
        CHECK(a / b == math_cases[i].quotient);
        CHECK(a % b == math_cases[i].remainder);
    }
    FAT16(); EXPECT(RB_VOLUME_OK);
    CHECK(r.fat_bits == 16 && r.clusters == 5000 && r.fat_sectors == 20
          && r.total_sectors == 5073 && r.data_lba == 173 && r.cluster_bytes == 512
          && disk.reads == 1 && disk.last_read == 100);
    FAT32(); EXPECT(RB_VOLUME_OK);
    CHECK(r.fat_bits == 32 && r.clusters == 70000 && r.fat_sectors == 547 && r.data_lba == 1226);
    for (i = 0; i < 8; ++i) {
        setup(&disk, &p, i < 4 ? 16 : 32, i < 4 ? 5000UL : 70000UL);
        p.type = types[i]; EXPECT(RB_VOLUME_OK);
    }
    FAT16(); p.logical = 1; p.table_lba = 37; EXPECT(RB_VOLUME_OK);
    FAT16(); p.type = 0x07; EXPECT(RB_VOLUME_UNSUPPORTED); CHECK(disk.reads == 0);
    FAT16(); p.type = 0x17; EXPECT(RB_VOLUME_UNSUPPORTED); CHECK(disk.reads == 0);
    FAT16(); p.type = 0x05; EXPECT(RB_VOLUME_UNSUPPORTED); CHECK(disk.reads == 0);
    FAT16(); p.start = 0; EXPECT(RB_VOLUME_RANGE); CHECK(disk.reads == 0);
    FAT16(); p.sectors = 0; EXPECT(RB_VOLUME_RANGE); CHECK(disk.reads == 0);
    FAT16(); p.start = 0xFFFFFFF0UL; EXPECT(RB_VOLUME_RANGE); CHECK(disk.reads == 0);
    FAT16(); CHECK(rb_probe_volume(&r, &p, read_mock, &disk, 0, 0) == RB_VOLUME_RANGE && disk.reads == 0);
    FAT16(); CHECK(rb_probe_volume(&r, &p, read_mock, &disk, p.start + p.sectors - 1, 0) == RB_VOLUME_RANGE && disk.reads == 0);
    FAT16(); CHECK(rb_probe_volume(&r, &p, read_mock, &disk, p.start + p.sectors, 0) == RB_VOLUME_OK);
    FAT16(); p.start = 0xFFFFFFFFUL - (p.sectors - 1); disk.lba = p.start;
    put32(disk.sector + 28, p.start); EXPECT(RB_VOLUME_OK);
    FAT16(); disk.io_error = 1; EXPECT(RB_VOLUME_IO); CHECK(disk.reads == 1);
    FAT16(); disk.sector[510] = 0; EXPECT(RB_VOLUME_SIGNATURE);
    FAT16(); disk.sector[511] = 0; EXPECT(RB_VOLUME_SIGNATURE);
    FAT16(); disk.sector[0] = 0; EXPECT(RB_VOLUME_JUMP);
    FAT16(); disk.sector[2] = 0; EXPECT(RB_VOLUME_JUMP);
    FAT16(); disk.sector[0] = 0xE9; disk.sector[2] = 0; EXPECT(RB_VOLUME_OK);
    FAT16(); put16(disk.sector + 11, 4096); EXPECT(RB_VOLUME_SECTOR);
    FAT16(); disk.sector[13] = 0; EXPECT(RB_VOLUME_CLUSTER);
    FAT16(); disk.sector[13] = 3; EXPECT(RB_VOLUME_CLUSTER);
    FAT16(); disk.sector[13] = 128; EXPECT(RB_VOLUME_CLUSTER);
    FAT16(); put16(disk.sector + 14, 0); EXPECT(RB_VOLUME_RESERVED);
    FAT16(); disk.sector[16] = 0; EXPECT(RB_VOLUME_FATS);
    FAT16(); disk.sector[21] = 0; EXPECT(RB_VOLUME_MEDIA);
    FAT16(); put32(disk.sector + 32, 0); EXPECT(RB_VOLUME_TOTAL);
    FAT16(); put16(disk.sector + 19, 100); EXPECT(RB_VOLUME_TOTAL);
    FAT16(); put16(disk.sector + 19, 5073); put32(disk.sector + 32, 0); EXPECT(RB_VOLUME_OK);
    FAT16(); ++p.sectors; EXPECT(RB_VOLUME_OK);
    FAT16(); --p.sectors; EXPECT(RB_VOLUME_TOTAL);
    FAT16(); put32(disk.sector + 28, 37); EXPECT(RB_VOLUME_HIDDEN);
    FAT16(); put16(disk.sector + 22, 0); EXPECT(RB_VOLUME_FAT_SIZE);
    FAT16(); put16(disk.sector + 14, 5073); EXPECT(RB_VOLUME_LAYOUT);
    FAT16(); put32(disk.sector + 32, 2); EXPECT(RB_VOLUME_LAYOUT);
    FAT32(); put32(disk.sector + 36, 0xFFFFFFFFUL); EXPECT(RB_VOLUME_LAYOUT);
    FAT32(); disk.sector[16] = 255; put32(disk.sector + 36, 0x01010102UL); EXPECT(RB_VOLUME_LAYOUT);
    FAT16(); put16(disk.sector + 22, 19); EXPECT(RB_VOLUME_FAT_SIZE);
    FAT32(); put32(disk.sector + 36, 546); EXPECT(RB_VOLUME_FAT_SIZE);
    FAT16(); put16(disk.sector + 17, 0); EXPECT(RB_VOLUME_ROOT);
    FAT32(); put16(disk.sector + 17, 16); EXPECT(RB_VOLUME_ROOT);
    setup(&disk, &p, 16, 4084); EXPECT(RB_VOLUME_TYPE);
    setup(&disk, &p, 16, 4085); EXPECT(RB_VOLUME_OK);
    setup(&disk, &p, 16, 65524); EXPECT(RB_VOLUME_OK);
    setup(&disk, &p, 16, 65525); EXPECT(RB_VOLUME_TYPE);
    setup(&disk, &p, 32, 65524); EXPECT(RB_VOLUME_TYPE);
    setup(&disk, &p, 32, 65525); EXPECT(RB_VOLUME_OK);
    setup(&disk, &p, 32, 0x0FFFFFEEUL); EXPECT(RB_VOLUME_OK);
    setup(&disk, &p, 32, 0x0FFFFFEFUL); EXPECT(RB_VOLUME_TYPE);
    FAT16(); p.type = 0x0B; EXPECT(RB_VOLUME_TYPE);
    FAT32(); p.type = 0x06; EXPECT(RB_VOLUME_TYPE);
    FAT32(); put16(disk.sector + 42, 1); EXPECT(RB_VOLUME_FAT32);
    FAT32(); put16(disk.sector + 40, 0x10); EXPECT(RB_VOLUME_FAT32);
    FAT32(); put16(disk.sector + 40, 0x82); EXPECT(RB_VOLUME_FAT32);
    FAT32(); put16(disk.sector + 40, 0x81); EXPECT(RB_VOLUME_OK);
    FAT32(); put16(disk.sector + 40, 0x0F); EXPECT(RB_VOLUME_OK);
    FAT32(); put32(disk.sector + 44, 1); EXPECT(RB_VOLUME_FAT32);
    FAT32(); put32(disk.sector + 44, 70002); EXPECT(RB_VOLUME_FAT32);
    FAT32(); put32(disk.sector + 44, 70001); EXPECT(RB_VOLUME_OK);
    FAT32(); put16(disk.sector + 48, 0); EXPECT(RB_VOLUME_FAT32);
    FAT32(); put16(disk.sector + 48, 32); EXPECT(RB_VOLUME_FAT32);
    FAT32(); put16(disk.sector + 50, 32); EXPECT(RB_VOLUME_FAT32);
    FAT32(); put16(disk.sector + 50, 1); EXPECT(RB_VOLUME_FAT32);
    FAT32(); put16(disk.sector + 50, 0); EXPECT(RB_VOLUME_OK);
    FAT16(); disk.sector[16] = 1; EXPECT(RB_VOLUME_OK);
    FAT16(); put16(disk.sector + 17, 17); EXPECT(RB_VOLUME_OK);
    /* A plausible header is still accepted with no label and no OS code. */
    FAT16(); disk.sector[54] = 'X'; EXPECT(RB_VOLUME_OK);
    report(number);
    return 0;
}
