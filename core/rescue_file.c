#include "rescue_file.h"

static rb_u8 fat[4608], sector[512], used[357];
static rb_u16 word(const rb_u8 *p) { return p[0] | ((rb_u16)p[1] << 8); }
static rb_u32 dword(const rb_u8 *p) { return word(p) | ((rb_u32)word(p + 2) << 16); }
static rb_u16 equal(const rb_u8 *a, const rb_u8 *b, rb_u16 n)
{
    while (n) { --n; if (a[n] != b[n]) { return 0; } }
    return 1;
}
static rb_u32 crc_update(rb_u32 crc, const rb_u8 *p)
{
    rb_u16 i, bit;
    for (i = 0; i < 512; ++i) {
        crc ^= p[i];
        for (bit = 0; bit < 8; ++bit) { crc = (crc >> 1) ^ ((crc & 1) ? 0xEDB88320UL : 0); }
    }
    return crc;
}
static void fail(rb_rescue_file *f, rb_u16 status, rb_u32 lba)
{
    rb_u16 i;
    f->status = status; f->error_lba = lba; f->ready = f->sectors = 0; f->metadata_crc = 0;
    for (i = 0; i < RB_FILE_MAX; ++i) { f->chain[i] = 0; }
}
static rb_u16 read_sector(rb_rescue_file *f, rb_u16 lba, rb_u8 *out)
{
    if (f->read(lba, out, f->opaque)) { fail(f, RB_FILE_IO, lba); return 1; }
    return 0;
}
static rb_u16 next(rb_u16 cluster)
{
    rb_u16 value = word(fat + cluster + cluster / 2);
    return cluster & 1 ? value >> 4 : value & 0xFFF;
}
static rb_u16 chain(rb_rescue_file *f, const rb_u8 *entry, rb_u16 target, rb_u16 lba)
{
    rb_u32 bytes = dword(entry + 28);
    rb_u16 count, i, cluster = word(entry + 26), value;
    if (bytes > 2847UL * 512 || (target && (bytes < 5UL * 512 || bytes > RB_FILE_MAX * 512UL || (bytes & 511)))) {
        fail(f, RB_FILE_SIZE, lba); return 1;
    }
    count = (rb_u16)((bytes + 511) / 512);
    if (!count && cluster) { fail(f, RB_FILE_CHAIN, lba); return 1; }
    for (i = 0; i < count; ++i) {
        if (cluster < 2 || cluster > 2848) { fail(f, RB_FILE_CHAIN, lba); return 1; }
        if (used[cluster / 8] & (1U << (cluster & 7))) { fail(f, RB_FILE_CROSSLINK, lba); return 1; }
        used[cluster / 8] |= (rb_u8)(1U << (cluster & 7));
        if (target) { f->chain[i] = cluster + 31; }
        value = next(cluster);
        if (i == count - 1 ? value < 0xFF8 : value < 2 || value > 2848) {
            fail(f, RB_FILE_CHAIN, lba); return 1;
        }
        cluster = value;
    }
    if (target) { f->sectors = count; }
    return 0;
}

void rb_rescue_file_open(rb_rescue_file *f, rb_sector_reader read, void *opaque)
{
    static const rb_u8 bpb[25] = {0,2,1,1,0,2,224,0,64,11,240,9,0,18,0,2,0,0,0,0,0,0,0,0,0};
    rb_u16 i, j, found = 0, end = 0, target;
    rb_u32 crc = 0xFFFFFFFFUL;
    const rb_u8 *entry;
    f->read = read; f->opaque = opaque; fail(f, RB_FILE_OK, 0);
    for (i = 0; i < sizeof(used); ++i) { used[i] = 0; }
    if (read_sector(f, 0, sector)) { return; }
    crc = crc_update(crc, sector);
    if (!equal(sector + 11, bpb, 25) || word(sector + 510) != 0xAA55
            || (sector[0] != 0xE9 && (sector[0] != 0xEB || sector[2] != 0x90))) {
        fail(f, RB_FILE_BPB, 0); return;
    }
    for (i = 0; i < 9; ++i) {
        if (read_sector(f, i + 1, fat + i * 512)) { return; }
        crc = crc_update(crc, fat + i * 512);
    }
    for (i = 0; i < 9; ++i) {
        if (read_sector(f, i + 10, sector)) { return; }
        crc = crc_update(crc, sector);
        if (!equal(sector, fat + i * 512, 512)) { fail(f, RB_FILE_FATS, i + 10); return; }
    }
    if (next(0) != 0xFF0 || next(1) < 0xFF8) { fail(f, RB_FILE_FATS, 1); return; }
    for (i = 19; i < 33; ++i) {
        if (read_sector(f, i, sector)) { return; }
        crc = crc_update(crc, sector);
        for (j = 0; j < 512 && !end; j += 32) {
            entry = sector + j;
            if (!entry[0]) { end = 1; break; }
            if (entry[0] == 0xE5 || entry[11] == 0x0F) { continue; }
            target = equal(entry, (const rb_u8 *)"RBBACKUPRBB", 11);
            if ((entry[11] & 0xD0) || word(entry + 20)
                    || ((entry[11] & 8) && (target || word(entry + 26) || dword(entry + 28)))) {
                fail(f, RB_FILE_DIRECTORY, i); return;
            }
            if (entry[11] & 8) { continue; }
            if (target && found++) { fail(f, RB_FILE_DUPLICATE, i); return; }
            if (chain(f, entry, target, i)) { return; }
        }
    }
    if (!found) { fail(f, RB_FILE_MISSING, 0); return; }
    f->metadata_crc = crc ^ 0xFFFFFFFFUL; f->ready = 1;
}

rb_u16 __cdecl rb_rescue_file_read(rb_u32 lba, rb_u8 *out, void *opaque)
{
    rb_rescue_file *f = (rb_rescue_file *)opaque;
    if (!f->ready || lba >= f->sectors) { fail(f, RB_FILE_RANGE, 0); return 1; }
    return read_sector(f, f->chain[(rb_u16)lba], out);
}
rb_u16 rb_rescue_file_recheck(rb_rescue_file *f)
{
    rb_u16 i;
    rb_u32 crc = 0xFFFFFFFFUL;
    if (!f->ready) { return 1; }
    for (i = 0; i < 33; ++i) {
        if (read_sector(f, i, sector)) { return 1; }
        crc = crc_update(crc, sector);
    }
    if ((crc ^ 0xFFFFFFFFUL) != f->metadata_crc) { fail(f, RB_FILE_CHANGED, 0); return 1; }
    return 0;
}
