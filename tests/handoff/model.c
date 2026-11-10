#include "handoff.h"
#include "handoff_fixture.h"

typedef struct {
    rb_u8 mbr[512], vbr[512];
    rb_u16 mbr_reads, vbr_reads, io, change_second;
} mock_disk;

static rb_u16 __cdecl read_mock(rb_u32 lba, rb_u8 *data, void *opaque)
{
    mock_disk *disk = (mock_disk *)opaque;
    rb_u8 *source;
    rb_u16 i;
    if (lba == 0) { source = disk->mbr; ++disk->mbr_reads; }
    else if (lba == 131072UL) { source = disk->vbr; ++disk->vbr_reads; }
    else { return 1; }
    for (i = 0; i < 512; ++i) { data[i] = source[i]; }
    if (disk->change_second && disk->vbr_reads > 1) { data[510] = 0; }
    return disk->io == 1 || (disk->io == 2 && lba != 0);
}

static void setup(mock_disk *disk, rb_handoff_target *target)
{
    rb_u16 i;
    rb_u8 *bytes = (rb_u8 *)disk;
    for (i = 0; i < sizeof(*disk); ++i) { bytes[i] = 0; }
    for (i = 0; i < 512; ++i) { disk->vbr[i] = rb_test_vbr[i]; }
    for (i = 0; i < 16; ++i) { disk->mbr[446 + i] = rb_test_entry[i]; }
    disk->mbr[440] = 0x31; disk->mbr[441] = 0x54;
    disk->mbr[442] = 0x42; disk->mbr[443] = 0x52;
    disk->mbr[510] = 0x55; disk->mbr[511] = 0xAA;
    target->slot = 1; target->disk_id = RB_TEST_DISK_ID;
    target->entry = rb_test_entry; target->sector = rb_test_vbr;
}

static rb_u16 cleared(const rb_handoff_buffer *r)
{
    rb_u16 i;
    const rb_u8 *bytes = (const rb_u8 *)r;
    for (i = 0; i < 528; ++i) { if (bytes[i] != 0) { return 0; } }
    return 1;
}

static rb_u16 report(rb_u16 n)
{
    const char digits[] = "0123456789ABCDEF";
    rb_putc('H'); rb_putc('='); rb_putc(digits[n >> 4]); rb_putc(digits[n & 15]);
    rb_putc(13); rb_putc(10);
    return n;
}

#define CHECK(c) do { ++n; if (!(c)) { return report(n); } } while (0)
#define RESET() setup(&disk, &target)
#define PREPARE() rb_prepare_handoff(&r, &target, read_mock, &disk, 262144UL, 0)
#define REJECT(s, d) CHECK(PREPARE() == (s) && r.status == (s) && r.detail == (d) && cleared(&r))

rb_u16 __cdecl rb_handoff_selftest(void)
{
    mock_disk disk;
    rb_handoff_target target;
    rb_handoff_buffer r;
    rb_u16 n = 0, i, same;
    RESET(); CHECK(PREPARE() == 0 && r.status == 0 && r.detail == 0);
    same = 1;
    for (i = 0; i < 512; ++i) { if (r.sector[i] != rb_test_vbr[i]) { same = 0; } }
    for (i = 0; i < 16; ++i) { if (r.entry[i] != rb_test_entry[i]) { same = 0; } }
    CHECK(same && disk.mbr_reads == 1 && disk.vbr_reads == 1);
    /* The exact header-validation read is retained, with no later reread. */
    RESET(); disk.change_second = 1; CHECK(PREPARE() == 0 && disk.vbr_reads == 1);
    /* A previous successful result cannot authorize changed media. */
    disk.vbr[509] ^= 1; REJECT(RB_HANDOFF_VOLUME, RB_VOLUME_SIGNATURE);
    RESET(); target.slot = 0; REJECT(RB_HANDOFF_TARGET, 0); CHECK(disk.mbr_reads == 0);
    RESET(); target.slot = 5; REJECT(RB_HANDOFF_TARGET, 0); CHECK(disk.mbr_reads == 0);
    RESET(); target.slot = 2; REJECT(RB_HANDOFF_TARGET, 0); CHECK(disk.vbr_reads == 0);
    RESET(); disk.mbr[440] ^= 1; REJECT(RB_HANDOFF_SCAN, RB_SCAN_IDENTITY);
    RESET(); disk.mbr[510] = 0; REJECT(RB_HANDOFF_SCAN, RB_SCAN_SIGNATURE);
    RESET(); disk.io = 1; REJECT(RB_HANDOFF_SCAN, RB_SCAN_IO); CHECK(disk.vbr_reads == 0);
    RESET(); disk.io = 2; REJECT(RB_HANDOFF_VOLUME, RB_VOLUME_IO);
    RESET(); disk.mbr[446] = 0; REJECT(RB_HANDOFF_TARGET, 0); CHECK(disk.vbr_reads == 0);
    RESET(); disk.mbr[450] = 0x16; REJECT(RB_HANDOFF_TARGET, 0);
    RESET(); disk.mbr[450] = 0x83; REJECT(RB_HANDOFF_SCAN, RB_SCAN_TYPE);
    RESET(); disk.mbr[447] ^= 1; REJECT(RB_HANDOFF_TARGET, 0);
    RESET(); disk.mbr[458] ^= 1; REJECT(RB_HANDOFF_TARGET, 0);
    RESET(); target.entry = disk.mbr + 462; REJECT(RB_HANDOFF_TARGET, 0); CHECK(disk.mbr_reads == 0);
    RESET(); disk.vbr[510] = 0; REJECT(RB_HANDOFF_VOLUME, RB_VOLUME_SIGNATURE);
    RESET(); disk.vbr[28] ^= 1; REJECT(RB_HANDOFF_VOLUME, RB_VOLUME_HIDDEN);
    RESET(); disk.vbr[509] ^= 1; REJECT(RB_HANDOFF_CODE, 0);
    RESET(); CHECK(rb_prepare_handoff(&r, &target, read_mock, &disk, 100UL, 0) == RB_HANDOFF_SCAN
                   && r.detail == RB_SCAN_RANGE && disk.vbr_reads == 0 && cleared(&r));
    RESET(); CHECK(PREPARE() == 0);
    disk.vbr[509] ^= 1; REJECT(RB_HANDOFF_CODE, 0);
    report(n);
    return 0;
}
