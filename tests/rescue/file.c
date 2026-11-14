#include "rescue_file.h"
#include "bios_ui.h"

static rb_u8 disk[33 * 512];
static struct { rb_u32 before; rb_rescue_file value; rb_u32 after; } guarded;
static struct { rb_u32 before; rb_u8 data[512]; rb_u32 after; } output;
static rb_u16 calls, io_at, change_at, bad_read;
static rb_u32 last_lba;

static void put16(rb_u8 *p, rb_u16 value) { p[0] = (rb_u8)value; p[1] = (rb_u8)(value >> 8); }
static void put32(rb_u8 *p, rb_u32 value) { put16(p, (rb_u16)value); put16(p + 2, (rb_u16)(value >> 16)); }
static void fat_set(rb_u16 cluster, rb_u16 value)
{
    rb_u8 *p = disk + 512 + cluster + cluster / 2;
    rb_u16 old = p[0] | ((rb_u16)p[1] << 8);
    put16(p, cluster & 1 ? (old & 15) | (value << 4) : (old & 0xF000) | value);
}
static void prepare(rb_u16 size, rb_u16 first, rb_u16 eoc)
{
    static const rb_u8 bpb[25] = {0,2,1,1,0,2,224,0,64,11,240,9,0,18,0,2,0,0,0,0,0,0,0,0,0};
    rb_u16 i;
    for (i = 0; i < sizeof(disk); ++i) { disk[i] = 0; }
    disk[0] = 0xEB; disk[2] = 0x90; disk[510] = 0x55; disk[511] = 0xAA;
    for (i = 0; i < 25; ++i) { disk[11 + i] = bpb[i]; }
    fat_set(0, 0xFF0); fat_set(1, 0xFFF); fat_set(2, 0xFFF);
    for (i = 0; i < size; ++i) { fat_set(first + i, i == size - 1 ? eoc : first + i + 1); }
    for (i = 0; i < 4608; ++i) { disk[5120 + i] = disk[512 + i]; }
    for (i = 0; i < 11; ++i) {
        disk[9728 + i] = ((const rb_u8 *)"RBRESCUEBIN")[i];
        disk[9760 + i] = ((const rb_u8 *)"RBBACKUPRBB")[i];
    }
    disk[9739] = disk[9771] = 0x20;
    put16(disk + 9754, 2); put32(disk + 9756, 512);
    put16(disk + 9786, first); put32(disk + 9788, size * 512UL);
}
static rb_u16 __cdecl read_mock(rb_u32 lba, rb_u8 *out, void *opaque)
{
    rb_u16 i;
    if (lba >= RB_FLOPPY_SECTORS || opaque != disk) { bad_read = 1; return 1; }
    ++calls; last_lba = lba;
    if (calls == io_at) { return 1; }
    for (i = 0; i < 512; ++i) { out[i] = lba < 33 ? disk[(rb_u16)lba * 512 + i] : (rb_u8)lba; }
    if (calls == change_at) { out[100] ^= 1; }
    return 0;
}
static void hex(rb_u16 value)
{
    rb_u16 i;
    static const char digits[] = "0123456789ABCDEF";
    for (i = 4; i; ) { --i; rb_debug_putc(digits[(value >> (i * 4)) & 15]); }
}
rb_u16 __cdecl rb_rescue_file_selftest(void)
{
    static const rb_u16 expected[8] = {0,0,11,5,10,1,1,0};
    rb_u16 mode, i, first, size, failures = 0, count = 0, code, valid;
    rb_rescue_file *f = &guarded.value;
    for (mode = 0; mode < 8; ++mode) {
        first = mode == 1 ? 100 : 12; size = mode == 1 ? RB_FILE_MAX : 5;
        prepare(size, first, mode == 7 ? 0xFF8 : 0xFFF);
        calls = bad_read = io_at = change_at = 0; last_lba = 0;
        guarded.before = output.before = 0x12345678UL; guarded.after = output.after = 0x87654321UL;
        rb_rescue_file_open(f, read_mock, disk);
        ++count;
        if (f->status || !f->ready || f->sectors != size || calls != 33) { ++failures; }
        code = 0;
        for (i = 0; i < 512; ++i) { output.data[i] = 0xA5; }
        if (mode == 2) { code = rb_rescue_file_read(size, output.data, f); }
        else if (mode == 3) { disk[9760] = 0xE5; rb_rescue_file_open(f, read_mock, disk); code = f->status; }
        else if (mode == 4 || mode == 5) {
            change_at = mode == 4 ? 34 : 0; io_at = mode == 5 ? 66 : 0;
            code = rb_rescue_file_recheck(f);
        } else if (mode == 6) { io_at = 34; code = rb_rescue_file_read(0, output.data, f); }
        else {
            code = rb_rescue_file_read(0, output.data, f);
            if (last_lba != first + 31 || output.data[511] != (rb_u8)last_lba) { code = 1; }
            code |= rb_rescue_file_read(size - 1, output.data, f);
            if (last_lba != first + size + 30 || output.data[511] != (rb_u8)last_lba) { code = 1; }
            code |= rb_rescue_file_recheck(f);
        }
        ++count;
        if (f->status != expected[mode] || !!code != !!expected[mode]) {
            ++failures; rb_debug_putc('!'); hex(mode); rb_debug_putc(':'); hex(f->status);
        }
        ++count; valid = 1;
        if (f->status) {
            if (f->ready || f->sectors || f->metadata_crc) { valid = 0; }
            for (i = 0; i < RB_FILE_MAX; ++i) { if (f->chain[i]) { valid = 0; } }
            if (f->error_lba != (mode == 5 ? 32UL : mode == 6 ? first + 31UL : 0)) { valid = 0; }
        } else if (!f->ready || f->sectors != size || f->chain[size - 1] != first + size + 30) { valid = 0; }
        if (!valid) { ++failures; }
        ++count;
        if (bad_read || guarded.before != 0x12345678UL || guarded.after != 0x87654321UL
                || output.before != 0x12345678UL || output.after != 0x87654321UL
                || calls != (mode == 2 ? 33 : mode == 6 ? 34 : expected[mode] ? 66 : 68)
                || ((mode == 2 || mode == 6) && output.data[511] != 0xA5)) { ++failures; }
    }
    rb_debug_putc('E'); rb_debug_putc('='); hex(count); rb_debug_putc('\r'); rb_debug_putc('\n');
    return failures;
}
