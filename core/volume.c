#include "volume.h"

static rb_u16 read16(const rb_u8 *p)
{
    return (rb_u16)p[0] | ((rb_u16)p[1] << 8);
}

static rb_u32 read32(const rb_u8 *p)
{
    return (rb_u32)read16(p) | ((rb_u32)read16(p + 2) << 16);
}

static rb_u16 fail(rb_volume_probe *r, rb_u16 status)
{
    r->status = status;
    return status;
}

/* BPB arithmetic follows Microsoft FAT 1.03. OEM/type labels are not evidence
 * of a filesystem. No FAT, directory, FSInfo or backup contents are read here. */
rb_u16 rb_probe_volume(rb_volume_probe *r, const rb_partition *p,
                      rb_sector_reader read, void *opaque, rb_u32 low, rb_u32 high)
{
    rb_u8 sector[512];
    rb_u8 *bytes = (rb_u8 *)r;
    rb_u16 i, expected, bits, spc, reserved, fats, root, total16, fat16, flags;
    rb_u16 fsinfo, backup;
    rb_u32 total, fat_size, root_sectors, remaining, first_data, clusters, root_cluster;
    for (i = 0; i < sizeof(*r); ++i) { bytes[i] = 0; }
    if (p->start == 0 || p->sectors == 0 || (low == 0 && high == 0)
            || p->sectors - 1 > 0xFFFFFFFFUL - p->start
            || (high == 0 && p->start + (p->sectors - 1) >= low)) {
        return fail(r, RB_VOLUME_RANGE);
    }
    if (p->type == 0x06U || p->type == 0x16U || p->type == 0x0EU || p->type == 0x1EU) {
        expected = 16;
    } else if (p->type == 0x0BU || p->type == 0x1BU || p->type == 0x0CU || p->type == 0x1CU) {
        expected = 32;
    } else {
        return fail(r, RB_VOLUME_UNSUPPORTED);
    }
    if (read(p->start, sector, opaque) != 0) { return fail(r, RB_VOLUME_IO); }
    if (sector[510] != 0x55 || sector[511] != 0xAA) { return fail(r, RB_VOLUME_SIGNATURE); }
    if (!(sector[0] == 0xEB && sector[2] == 0x90) && sector[0] != 0xE9) {
        return fail(r, RB_VOLUME_JUMP);
    }
    if (read16(sector + 11) != 512) { return fail(r, RB_VOLUME_SECTOR); }
    spc = sector[13];
    if (spc == 0 || spc > 64 || (spc & (spc - 1)) != 0) { return fail(r, RB_VOLUME_CLUSTER); }
    reserved = read16(sector + 14);
    if (reserved == 0) { return fail(r, RB_VOLUME_RESERVED); }
    fats = sector[16];
    if (fats == 0) { return fail(r, RB_VOLUME_FATS); }
    if (sector[21] != 0xF0 && sector[21] < 0xF8) { return fail(r, RB_VOLUME_MEDIA); }
    total16 = read16(sector + 19);
    total = read32(sector + 32);
    if (total16 != 0) {
        if (total != 0) { return fail(r, RB_VOLUME_TOTAL); }
        total = total16;
    }
    if (total == 0 || total > p->sectors) { return fail(r, RB_VOLUME_TOTAL); }
    if (read32(sector + 28) != p->start) { return fail(r, RB_VOLUME_HIDDEN); }
    root = read16(sector + 17);
    fat16 = read16(sector + 22);
    fat_size = fat16 != 0 ? (rb_u32)fat16 : read32(sector + 36);
    if (fat_size == 0) { return fail(r, RB_VOLUME_FAT_SIZE); }
    root_sectors = ((rb_u32)root * 32 + 511) / 512;
    /* Subtract only after bounds checks; bound multiplication by division. */
    if ((rb_u32)reserved >= total) { return fail(r, RB_VOLUME_LAYOUT); }
    remaining = total - reserved;
    if (root_sectors >= remaining) { return fail(r, RB_VOLUME_LAYOUT); }
    remaining -= root_sectors;
    if (fat_size > remaining / fats) { return fail(r, RB_VOLUME_LAYOUT); }
    first_data = (rb_u32)reserved + root_sectors + (rb_u32)fats * fat_size;
    if (first_data >= total) { return fail(r, RB_VOLUME_LAYOUT); }
    clusters = (total - first_data) / spc;
    bits = clusters < 4085UL ? 12 : clusters < 65525UL ? 16 : 32;
    if (bits != expected || clusters >= 0x0FFFFFEFUL
            || (bits == 16 && fat16 == 0) || (bits == 32 && fat16 != 0)) {
        return fail(r, RB_VOLUME_TYPE);
    }
    if ((bits == 16 && root == 0) || (bits == 32 && root != 0)) {
        return fail(r, RB_VOLUME_ROOT);
    }
    /* Include the two reserved FAT entries; division avoids byte-size overflow. */
    if (fat_size < (clusters + 2 + (bits == 16 ? 255UL : 127UL)) / (bits == 16 ? 256UL : 128UL)) {
        return fail(r, RB_VOLUME_FAT_SIZE);
    }
    if (bits == 32) {
        flags = read16(sector + 40);
        root_cluster = read32(sector + 44);
        fsinfo = read16(sector + 48);
        backup = read16(sector + 50);
        if (total16 != 0 || read16(sector + 42) != 0 || (flags & 0xFF70U) != 0
                || ((flags & 0x80U) != 0 && (flags & 15U) >= fats)
                || root_cluster < 2 || root_cluster > clusters + 1
                || fsinfo == 0 || fsinfo >= reserved
                || (backup != 0 && (backup >= reserved || backup == fsinfo))) {
            return fail(r, RB_VOLUME_FAT32);
        }
    }
    r->fat_bits = bits;
    r->cluster_bytes = spc * 512U;
    r->fats = fats;
    r->total_sectors = total;
    r->clusters = clusters;
    r->data_lba = p->start + first_data;
    r->fat_sectors = fat_size;
    return RB_VOLUME_OK;
}
