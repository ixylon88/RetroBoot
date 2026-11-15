#include "backup_format.h"

static rb_u16 zeros(const rb_u8 *p, rb_u16 n)
{
    while (n) { if (p[--n]) { return 0; } }
    return 1;
}
rb_u32 rb_backup_crc_update(rb_u32 crc, const rb_u8 *p, rb_u16 n)
{
    rb_u16 bit;
    while (n--) {
        crc ^= *p++;
        for (bit = 0; bit < 8; ++bit) {
            crc = (crc >> 1) ^ ((crc & 1) ? 0xEDB88320UL : 0);
        }
    }
    return crc;
}
static rb_u16 range(rb_u32 start, rb_u32 n, const rb_backup *r)
{
    return n && start <= 0xFFFFFFFFUL - n
        && (r->capacity_high || start + n <= r->capacity_low);
}
rb_u16 rb_backup_identity(const rb_backup *r, rb_u32 size)
{
    if (size < 5 || size > RB_BACKUP_SECTORS || !r->count || r->count > RB_BACKUP_MAX) {
        return RB_BACKUP_FORMAT;
    }
    if (!r->generation || !r->disk_id || zeros(r->media_id, 16)
            || (r->route != 1 && r->route != 2)
            || ((r->route == 2 || r->heads || r->sectors_per_track) && (!r->heads || r->heads > 256
                || !r->sectors_per_track || r->sectors_per_track > 63))) { return RB_BACKUP_FORMAT; }
    if (!r->admin_start || !range(r->admin_start, r->admin_sectors, r)) { return RB_BACKUP_RANGE; }
    if (r->route == 2 && (r->capacity_high || r->capacity_low > 1024UL * r->heads * r->sectors_per_track)) {
        return RB_BACKUP_RANGE;
    }
    return RB_BACKUP_OK;
}

rb_u16 rb_backup_entries(const rb_backup *r, rb_u32 size)
{
    rb_u16 i, j, kind, index, previous = 0, next_index = 0, mask = 0;
    rb_u32 next = 5;
    const rb_backup_extent *e, *other;
    for (i = 0; i < r->count; ++i) {
        e = &r->entries[i]; kind = e->kind; index = e->index;
        if (kind < 1 || kind > 8) { return RB_BACKUP_FORMAT; }
        if (kind < previous) { return RB_BACKUP_ORDER; }
        if (kind != previous) { next_index = 0; }
        if (index != next_index++ || (kind != RB_BACKUP_EBR && kind != RB_BACKUP_BOOT && index)
                || (kind == RB_BACKUP_EBR && index >= 16)
                || (kind == RB_BACKUP_BOOT && index >= 20)) { return RB_BACKUP_ORDER; }
        previous = kind; mask |= 1U << kind;
        if (!range(e->lba, e->sectors, r) || e->file_sector != next
                || e->sectors > size - next) { return RB_BACKUP_RANGE; }
        next += e->sectors;
        if (kind <= RB_BACKUP_EBR) {
            if (e->sectors != 1 || e->owner_start || e->owner_sectors
                    || (kind <= RB_BACKUP_APPROVED ? e->lba != 0 : e->lba == 0)) { return RB_BACKUP_RANGE; }
        } else {
            if (!e->owner_start || !range(e->owner_start, e->owner_sectors, r)
                    || e->lba < e->owner_start || e->lba + e->sectors > e->owner_start + e->owner_sectors) {
                return RB_BACKUP_RANGE;
            }
            if (kind != RB_BACKUP_BOOT && (e->sectors != 1 || e->owner_start != r->admin_start
                    || e->owner_sectors != r->admin_sectors)) { return RB_BACKUP_RANGE; }
        }
        for (j = 0; j < i; ++j) {
            other = &r->entries[j];
            if (kind == RB_BACKUP_APPROVED && other->kind == RB_BACKUP_ORIGINAL) { continue; }
            if (e->lba < other->lba + other->sectors && other->lba < e->lba + e->sectors) {
                return RB_BACKUP_OVERLAP;
            }
        }
    }
    /* Both MBRs, at least one boot area, config A/B and state A/B. EBRs optional. */
    if ((mask & 0x1F6) != 0x1F6) { return RB_BACKUP_MISSING; }
    if (next != size) { return RB_BACKUP_RANGE; }
    return RB_BACKUP_OK;
}
