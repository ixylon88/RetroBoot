#include "backup_boot.h"
#include "backup_saved.h"
#include "volume.h"
#include "fat_boot.h"

typedef struct { rb_u32 lba; const rb_u8 *data; } rb_saved_first;

static rb_u16 word(const rb_u8 *p) { return p[0] | ((rb_u16)p[1] << 8); }
static void copy(rb_u8 *out, const rb_u8 *in)
{
    rb_u16 i;
    for (i = 0; i < 512; ++i) { out[i] = in[i]; }
}
static rb_u16 equal(const rb_u8 *a, const rb_u8 *b)
{
    rb_u16 i;
    for (i = 0; i < 512; ++i) { if (a[i] != b[i]) { return 0; } }
    return 1;
}
static rb_u32 crc_update(rb_u32 crc, const rb_u8 *p)
{
    rb_u16 i, bit;
    for (i = 0; i < 512; ++i) {
        crc ^= p[i];
        for (bit = 0; bit < 8; ++bit) {
            crc = (crc >> 1) ^ ((crc & 1) ? 0xEDB88320UL : 0);
        }
    }
    return crc;
}
static void fail(rb_backup_boot *r, rb_u16 code, rb_u16 detail,
                 rb_u16 index, rb_u32 lba)
{
    rb_u16 i;
    for (i = 0; i < sizeof(*r); ++i) { ((rb_u8 *)r)[i] = 0; }
    r->status = code; r->detail = detail; r->kind = RB_BACKUP_BOOT;
    r->index = index; r->error_lba = lba;
}
static const rb_backup_extent *find(const rb_backup_saved *s, rb_u32 lba, rb_u32 owner)
{
    rb_u16 i;
    const rb_backup_extent *e;
    for (i = 0; i < s->container.count; ++i) {
        e = &s->container.entries[i];
        if (e->kind == RB_BACKUP_BOOT && e->lba == lba && e->owner_start == owner) { return e; }
    }
    return (const rb_backup_extent *)0;
}
static rb_u16 read_sector(rb_backup_boot *r, const rb_backup_saved *s,
                         const rb_backup_extent *e, rb_u32 offset, rb_u8 *out)
{
    if (s->read(e->file_sector + offset, out, s->opaque)) {
        fail(r, RB_BBOOT_IO, 0, e->index, e->lba + offset); return 1;
    }
    return 0;
}
/* The volume parser receives the already captured first sector. */
static rb_u16 __cdecl read_first(rb_u32 lba, rb_u8 *out, void *opaque)
{
    const rb_saved_first *first = (const rb_saved_first *)opaque;
    if (lba != first->lba) { return 1; }
    copy(out, first->data); return 0;
}
const rb_backup *rb_backup_open_boot(rb_backup_boot *r, rb_sector_reader read, void *opaque, rb_u32 size)
{
    rb_backup_records records;
    rb_volume_probe volume;
    rb_backup_saved *s;
    rb_saved_first captured;
    rb_u8 *sector, *first, *continuation;
    const rb_backup_extent *e, *start;
    const rb_partition *p;
    const rb_installation *installation;
    rb_u16 i, j, code, reserved, backup, volumes = 0, fat16 = 0, fat32 = 0, ready = 0, total = 0;
    rb_u32 cursor, offset, relative, crc, vbr_crc;
    fail(r, RB_BBOOT_OK, 0, 0, 0); r->kind = 0;
    s = rb_backup_open_records(&records, read, opaque, size);
    if (!s) {
        fail(r, RB_BBOOT_RECORDS, records.status, records.index, records.error_lba);
        r->kind = records.kind; r->record_detail = records.detail; return (const rb_backup *)0;
    }
    /* No record-sector byte is used after the successful record check.
       Each boot buffer is filled before use, including after a failed call. */
    sector = s->scratch.boot.sector; first = s->scratch.boot.first;
    continuation = s->scratch.boot.continuation;
    captured.data = first;
    for (i = 0; i < s->scan.count; ++i) {
        p = &s->scan.entries[i];
        if (!p->type || p->type == 5 || p->type == 15) { continue; }
        start = find(s, p->start, p->start); /* Checked by the record layer. */
        if (read_sector(r, s, start, 0, sector)) { return (const rb_backup *)0; }
        copy(first, sector);
        captured.lba = p->start;
        code = rb_probe_volume(&volume, p, read_first, &captured,
            s->container.capacity_low, s->container.capacity_high);
        if (code) { fail(r, RB_BBOOT_VOLUME, code, start->index, p->start); return (const rb_backup *)0; }
        reserved = word(first + 14); backup = 0;
        if (volume.fat_bits == 32) {
            backup = word(first + 50);
            if (word(first + 48) != 1 || reserved < 3
                    || (backup && (backup < 3 || (rb_u32)backup + 3 > reserved))) {
                fail(r, RB_BBOOT_FAT32_LAYOUT, 0, start->index, p->start); return (const rb_backup *)0;
            }
        }
        /* Non-overlap and owner identity were checked earlier. Reject extras
           outside the reserved area; a contiguous walk below detects holes. */
        for (j = 0; j < s->container.count; ++j) {
            e = &s->container.entries[j];
            if (e->kind == RB_BACKUP_BOOT && e->owner_start == p->start
                    && (e->lba - p->start >= reserved || e->sectors > reserved - (e->lba - p->start))) {
                fail(r, RB_BBOOT_COVERAGE, 2, e->index, e->lba); return (const rb_backup *)0;
            }
        }
        cursor = p->start;
        while (cursor - p->start < reserved) {
            e = find(s, cursor, p->start);
            if (!e) { fail(r, RB_BBOOT_COVERAGE, 1, RB_CONFIG_NONE, cursor); return (const rb_backup *)0; }
            cursor += e->sectors;
        }
        cursor = p->start;
        while (cursor - p->start < reserved) {
            e = find(s, cursor, p->start);
            crc = 0xFFFFFFFFUL;
            for (offset = 0; offset < e->sectors; ++offset) {
                relative = cursor + offset - p->start;
                if (!relative) { copy(sector, first); }
                else if (read_sector(r, s, e, offset, sector)) { return (const rb_backup *)0; }
                crc = crc_update(crc, sector);
                if (volume.fat_bits != 32) { continue; }
                if (relative == 1 || (backup && relative == (rb_u32)backup + 1)) {
                    code = rb_fat32_fsinfo(sector, volume.clusters);
                    if (code) { fail(r, RB_BBOOT_FSINFO, code, e->index, cursor + offset); return (const rb_backup *)0; }
                } else if (relative == 2) {
                    if (word(sector + 510) != 0xAA55) {
                        fail(r, RB_BBOOT_COPY, 3, e->index, cursor + offset); return (const rb_backup *)0;
                    }
                    copy(continuation, sector);
                } else if (backup && (relative == backup || relative == (rb_u32)backup + 2)) {
                    if (!equal(sector, relative == backup ? first : continuation)) {
                        fail(r, RB_BBOOT_COPY, relative == backup ? 1 : 2, e->index, cursor + offset); return (const rb_backup *)0;
                    }
                }
            }
            if ((crc ^ 0xFFFFFFFFUL) != e->crc) {
                fail(r, RB_BBOOT_CHANGED, 0, e->index, e->lba); return (const rb_backup *)0;
            }
            cursor += e->sectors;
        }
        vbr_crc = rb_crc32(first, 512);
        for (j = 0; j < s->state.state.count; ++j) {
            installation = &s->state.state.entries[j];
            if (installation->phase == RB_INSTALL_READY && installation->start == p->start) {
                if (installation->vbr_crc != vbr_crc) {
                    fail(r, RB_BBOOT_READY, j, start->index, p->start); return (const rb_backup *)0;
                }
                ++ready;
            }
        }
        ++volumes; total += reserved;
        if (volume.fat_bits == 16) { ++fat16; } else { ++fat32; }
    }
    r->volumes = volumes; r->fat16 = fat16; r->fat32 = fat32;
    r->reserved_sectors = total; r->ready_matches = ready;
    return &s->container;
}

void rb_backup_check_boot(rb_backup_boot *r, rb_sector_reader read, void *opaque, rb_u32 size)
{
    (void)rb_backup_open_boot(r, read, opaque, size);
}
