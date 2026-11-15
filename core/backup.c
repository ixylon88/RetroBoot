#include "backup.h"
#include "backup_format.h"

static rb_u8 sector[512];

static rb_u16 word(const rb_u8 *p) { return p[0] | ((rb_u16)p[1] << 8); }
static rb_u32 dword(const rb_u8 *p) { return word(p) | ((rb_u32)word(p + 2) << 16); }
static rb_u16 zeros(const rb_u8 *p, rb_u16 n)
{
    while (n) { if (p[--n]) { return 0; } }
    return 1;
}
static rb_u16 validate(rb_backup *r, rb_sector_reader read, void *opaque, rb_u32 size)
{
    static const rb_u8 magic[8] = {'R','B','B','A','K',0,0,0};
    rb_u16 i, j, slot, status;
    rb_u32 crc, table_crc, pos;
    rb_backup_extent *e;
    const rb_u8 *p;
    if (size < 5 || size > RB_BACKUP_SECTORS) { return RB_BACKUP_FORMAT; }
    if (read(0, sector, opaque)) { return RB_BACKUP_IO; }
    for (i = 0; i < 8; ++i) { if (sector[i] != magic[i]) { return RB_BACKUP_FORMAT; } }
    r->count = word(sector + 36);
    if (word(sector + 8) != 1 || word(sector + 10) != 512
            || dword(sector + 12) != size * 512UL
            || !r->count || r->count > RB_BACKUP_MAX || word(sector + 38) != 32
            || word(sector + 46) || !zeros(sector + 76, 432)) { return RB_BACKUP_FORMAT; }
    if ((rb_backup_crc_update(0xFFFFFFFFUL, sector, 508) ^ 0xFFFFFFFFUL) != dword(sector + 508)) {
        return RB_BACKUP_CRC;
    }
    r->generation = dword(sector + 16); r->disk_id = dword(sector + 20);
    r->layout_crc = dword(sector + 24);
    r->admin_start = dword(sector + 28); r->admin_sectors = dword(sector + 32);
    r->route = word(sector + 40); r->heads = word(sector + 42);
    r->sectors_per_track = word(sector + 44);
    r->capacity_low = dword(sector + 48); r->capacity_high = dword(sector + 52);
    for (i = 0; i < 16; ++i) { r->media_id[i] = sector[56 + i]; }
    table_crc = dword(sector + 72);
    status = rb_backup_identity(r, size);
    if (status) { return status; }
    crc = 0xFFFFFFFFUL;
    for (i = 0; i < 4; ++i) {
        if (read((rb_u32)i + 1, sector, opaque)) { return RB_BACKUP_IO; }
        crc = rb_backup_crc_update(crc, sector, 512);
        for (j = 0; j < 16; ++j) {
            slot = i * 16 + j; p = sector + j * 32;
            if (slot >= r->count) {
                if (!zeros(p, 32)) { return RB_BACKUP_FORMAT; }
            } else {
                if (dword(p + 28)) { return RB_BACKUP_FORMAT; }
                e = &r->entries[slot]; e->kind = word(p); e->index = word(p + 2);
                e->lba = dword(p + 4); e->sectors = dword(p + 8);
                e->file_sector = dword(p + 12); e->crc = dword(p + 16);
                e->owner_start = dword(p + 20); e->owner_sectors = dword(p + 24);
            }
        }
    }
    if ((crc ^ 0xFFFFFFFFUL) != table_crc) { return RB_BACKUP_CRC; }
    status = rb_backup_entries(r, size);
    if (status) { return status; }
    for (i = 0; i < r->count; ++i) {
        e = &r->entries[i]; crc = 0xFFFFFFFFUL;
        for (pos = 0; pos < e->sectors; ++pos) {
            if (read(e->file_sector + pos, sector, opaque)) { return RB_BACKUP_IO; }
            crc = rb_backup_crc_update(crc, sector, 512);
        }
        if ((crc ^ 0xFFFFFFFFUL) != e->crc) { return RB_BACKUP_CRC; }
    }
    return RB_BACKUP_OK;
}

rb_u16 rb_backup_validate(rb_backup *r, rb_sector_reader read, void *opaque, rb_u32 size)
{
    rb_u16 i, status;
    rb_u8 *p = (rb_u8 *)r;
    for (i = 0; i < sizeof(*r); ++i) { p[i] = 0; }
    status = validate(r, read, opaque, size);
    if (status) { for (i = 0; i < sizeof(*r); ++i) { p[i] = 0; } }
    return status;
}
