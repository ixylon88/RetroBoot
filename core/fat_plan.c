#include "fat_plan.h"

static rb_u16 matches_chs(const rb_u8 *field, rb_u32 lba, const rb_u16 *g)
{
    rb_u32 track = lba / g[2];
    rb_u16 cylinder = field[2] | ((rb_u16)(field[1] & 0xC0U) << 2);
    return cylinder == track / g[1] && field[0] == track % g[1]
        && (field[1] & 63U) == 1 + lba % g[2];
}

static rb_u16 layout(rb_fat_plan *out, const rb_partition *p, rb_u16 bits, rb_u16 spc)
{
    rb_u16 reserved = bits == 16 ? 1 : 32;
    rb_u16 root_sectors = bits == 16 ? 32 : 0; /* 512 fixed FAT16 entries. */
    rb_u16 entries_per_sector = bits == 16 ? 256 : 128;
    rb_u32 minimum = bits == 16 ? 4085UL : 65525UL;
    rb_u32 available, fat, clusters;
    if (p->sectors <= reserved + root_sectors) { return RB_FORMAT_CLUSTER_COUNT; }
    available = p->sectors - reserved - root_sectors;
    /* Budget entries for all potential clusters and the two reserved entries,
       then derive the real data-cluster count after subtracting both FATs. */
    if (available < minimum * spc) { return RB_FORMAT_CLUSTER_COUNT; }
    fat = 1 + (available / spc + 1) / entries_per_sector;
    /* At the lower cutover a conservative table can consume enough sectors
       to push an otherwise valid volume into the preceding FAT family. */
    if (fat > (available - minimum * spc) / 2) {
        fat = (available - minimum * spc) / 2;
    }
    clusters = (available - 2 * fat) / spc;
    if (fat <= (clusters + 1) / entries_per_sector
            || (bits == 16 ? clusters >= 65525UL || fat > 65535UL : clusters >= 0x0FFFFFEFUL)) {
        return RB_FORMAT_CLUSTER_COUNT;
    }
    out->bits = bits; out->spc = spc; out->reserved = reserved;
    out->sectors_per_fat = fat; out->clusters = clusters;
    out->fat1 = p->start + reserved; out->fat2 = out->fat1 + fat;
    out->root = out->fat2 + fat;
    out->data = out->root + root_sectors; /* FAT32 root cluster 2 starts here. */
    return RB_FORMAT_OK;
}

rb_u16 rb_plan_primary_fat(rb_fat_plan *out, const rb_partition *p, const rb_u8 *entry,
    const rb_rescue_device *disk, const rb_u16 *g, rb_u16 spc)
{
    rb_u16 i, base = p->type & ~0x10U, bits;
    rb_u32 last;
    rb_u8 *bytes = (rb_u8 *)out;
    for (i = 0; i < sizeof(*out); ++i) { bytes[i] = 0; }
    if (p->logical || p->slot < 1 || p->slot > 4 || p->table_lba != 0
            || (base != 0x06 && base != 0x0B && base != 0x0E && base != 0x0C)) {
        return RB_FORMAT_TARGET;
    }
    if (!p->start || !p->sectors || p->sectors - 1 > 0xFFFFFFFFUL - p->start) { return RB_FORMAT_RANGE; }
    last = p->start + (p->sectors - 1);
    if (!disk->capacity_high && last >= disk->capacity_low) { return RB_FORMAT_RANGE; }
    if (base == 0x0E || base == 0x0C) {
        if (disk->mode != 1) { return RB_FORMAT_EDD; }
    } else if (!g[0] || g[0] > 1024 || !g[1] || g[1] > 256 || !g[2] || g[2] > 63
            || last >= (rb_u32)g[0] * g[1] * g[2]
            || !matches_chs(entry + 1, p->start, g) || !matches_chs(entry + 5, last, g)) {
        return RB_FORMAT_CHS;
    }
    bits = base == 0x06 || base == 0x0E ? 16 : 32;
    if (spc) {
        if (spc > 64 || (spc & (spc - 1))) { return RB_FORMAT_CLUSTER_SIZE; }
        return layout(out, p, bits, spc);
    }
    /* The reference FAT32 profiles use 4 KiB clusters. Smaller DOS FAT16
       volumes and FAT32 volumes below that range can use smaller clusters. */
    if (bits == 32 && layout(out, p, bits, 8) == RB_FORMAT_OK) { return RB_FORMAT_OK; }
    for (spc = 1; spc <= 64; spc *= 2) {
        if (layout(out, p, bits, spc) == RB_FORMAT_OK) { return RB_FORMAT_OK; }
    }
    return RB_FORMAT_CLUSTER_COUNT;
}
