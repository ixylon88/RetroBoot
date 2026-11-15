#include "backup_encode.h"
#include "backup_format.h"

static void clear(rb_u8 *p)
{
    rb_u16 i;
    for (i = 0; i < 512; ++i) { p[i] = 0; }
}
static void put16(rb_u8 *p, rb_u16 value)
{
    p[0] = (rb_u8)value; p[1] = (rb_u8)(value >> 8);
}
static void put32(rb_u8 *p, rb_u32 value)
{
    put16(p, (rb_u16)value); put16(p + 2, (rb_u16)(value >> 16));
}
static void table(const rb_backup *b, rb_u16 page, rb_u8 *out)
{
    rb_u16 i, slot;
    rb_u8 *p;
    const rb_backup_extent *e;
    clear(out);
    for (i = 0; i < 16; ++i) {
        slot = page * 16 + i;
        if (slot >= b->count) { break; }
        e = &b->entries[slot]; p = out + i * 32;
        put16(p, e->kind); put16(p + 2, e->index);
        put32(p + 4, e->lba); put32(p + 8, e->sectors);
        put32(p + 12, e->file_sector); put32(p + 16, e->crc);
        put32(p + 20, e->owner_start); put32(p + 24, e->owner_sectors);
    }
}

rb_u16 rb_backup_encode_metadata(const rb_backup *b, rb_u32 size,
    rb_u16 pos, rb_u8 *out)
{
    static const rb_u8 magic[8] = {'R','B','B','A','K',0,0,0};
    rb_u16 i, status;
    rb_u32 crc;
    if (!out) { return RB_BACKUP_FORMAT; }
    clear(out);
    if (!b || pos > 4) { return RB_BACKUP_FORMAT; }
    status = rb_backup_identity(b, size);
    if (!status) { status = rb_backup_entries(b, size); }
    if (status) { return status; }
    if (pos) { table(b, pos - 1, out); return RB_BACKUP_OK; }

    /* Reuse the caller's sector for all four table pages, then the header.
       There is no second sector buffer and no cache of a previous call. */
    crc = 0xFFFFFFFFUL;
    for (i = 0; i < 4; ++i) {
        table(b, i, out); crc = rb_backup_crc_update(crc, out, 512);
    }
    clear(out);
    for (i = 0; i < 8; ++i) { out[i] = magic[i]; }
    put16(out + 8, 1); put16(out + 10, 512); put32(out + 12, size * 512UL);
    put32(out + 16, b->generation); put32(out + 20, b->disk_id);
    put32(out + 24, b->layout_crc); put32(out + 28, b->admin_start);
    put32(out + 32, b->admin_sectors); put16(out + 36, b->count);
    put16(out + 38, 32); put16(out + 40, b->route);
    put16(out + 42, b->heads); put16(out + 44, b->sectors_per_track);
    put32(out + 48, b->capacity_low); put32(out + 52, b->capacity_high);
    for (i = 0; i < 16; ++i) { out[56 + i] = b->media_id[i]; }
    put32(out + 72, crc ^ 0xFFFFFFFFUL);
    put32(out + 508, rb_backup_crc_update(0xFFFFFFFFUL, out, 508) ^ 0xFFFFFFFFUL);
    return RB_BACKUP_OK;
}
