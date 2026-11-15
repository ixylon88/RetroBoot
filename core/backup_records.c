#include "backup_saved.h"
#include "backup_links.h"

static rb_backup_saved saved;

static void clear(void *p, rb_u16 n)
{
    rb_u8 *bytes = (rb_u8 *)p;
    while (n) { bytes[--n] = 0; }
}
static rb_u32 dword(const rb_u8 *p)
{
    return (rb_u32)p[0] | ((rb_u32)p[1] << 8) | ((rb_u32)p[2] << 16) | ((rb_u32)p[3] << 24);
}
static rb_u16 equal(const rb_u8 *a, const rb_u8 *b, rb_u16 n)
{
    while (n) { --n; if (a[n] != b[n]) { return 0; } }
    return 1;
}
static void fail(rb_backup_records *r, rb_u16 status, rb_u16 detail,
                 rb_u16 kind, rb_u16 index, rb_u32 lba)
{
    clear(r, sizeof(*r)); r->status = status; r->detail = detail;
    r->kind = kind; r->index = index; r->error_lba = lba;
    r->config_source = r->state_source = RB_CONFIG_NONE;
}
static const rb_backup_extent *find(rb_u16 kind)
{
    rb_u16 i;
    for (i = 0; i < saved.container.count; ++i) {
        if (saved.container.entries[i].kind == kind) { return &saved.container.entries[i]; }
    }
    return (const rb_backup_extent *)0;
}
/* Semantic readers consume only complete one-sector records and recheck the
   container's payload CRC, including MBR fields omitted from RBL1. */
static rb_u16 read_record(const rb_backup_extent *e, rb_u8 *out)
{
    saved.kind = e->kind; saved.index = e->index; saved.lba = e->lba;
    if (saved.read(e->file_sector, out, saved.opaque)) { saved.read_status = RB_BREC_IO; return 1; }
    if (rb_crc32(out, 512) != e->crc) { saved.read_status = RB_BREC_CHANGED; return 1; }
    return 0;
}
static rb_u16 __cdecl read_table(rb_u32 lba, rb_u8 *out, void *opaque)
{
    rb_u16 i;
    const rb_backup_extent *e;
    (void)opaque;
    for (i = 0; i < saved.container.count; ++i) {
        e = &saved.container.entries[i];
        if (e->lba == lba && e->kind == (lba ? RB_BACKUP_EBR : RB_BACKUP_APPROVED)) {
            if (read_record(e, out)) { return 1; }
            if (!lba) { for (i = 0; i < 512; ++i) { saved.scratch.records.mbr[i] = out[i]; } }
            return 0;
        }
    }
    saved.read_status = RB_BREC_COVERAGE; saved.kind = RB_BACKUP_EBR;
    saved.index = RB_CONFIG_NONE; saved.lba = lba;
    return 1;
}
static void read_failure(rb_backup_records *r)
{
    fail(r, saved.read_status, saved.read_status == RB_BREC_COVERAGE ? RB_BREC_MISSING_EBR : 0,
         saved.kind, saved.index, saved.lba);
}
static rb_u16 data_partition(const rb_partition *p)
{
    return p->type && p->type != 5 && p->type != 15;
}
static rb_u16 load_pair(rb_backup_records *r, rb_u16 kind, const rb_partition *admin)
{
    rb_u16 i, code, status;
    const rb_backup_extent *e;
    rb_u8 *data;
    for (i = 0; i < 2; ++i) {
        e = find(kind + i); /* Required singleton roles were checked by container validation. */
        if (read_record(e, i ? saved.scratch.records.b : saved.scratch.records.a)) { read_failure(r); return 1; }
    }
    if (kind == RB_BACKUP_CONFIG_A) {
        rb_config_select(&saved.config, saved.scratch.records.a, saved.scratch.records.b, 3, &saved.scan, admin);
        status = saved.config.status;
    } else {
        rb_state_select(&saved.state, saved.scratch.records.a, saved.scratch.records.b, 3, &saved.scan, admin);
        status = saved.state.status;
    }
    for (i = 0; i < 2; ++i) {
        code = kind == RB_BACKUP_CONFIG_A ? saved.config.copies[i] : saved.state.copies[i];
        if (code) {
            e = find(kind + i);
            fail(r, kind == RB_BACKUP_CONFIG_A ? RB_BREC_CONFIG : RB_BREC_STATE, code, kind + i, 0, e->lba);
            return 1;
        }
    }
    if (status) {
        fail(r, kind == RB_BACKUP_CONFIG_A ? RB_BREC_CONFIG : RB_BREC_STATE, status, kind, 0, find(kind)->lba);
        return 1;
    }
    for (i = 0; i < 2; ++i) {
        data = i ? saved.scratch.records.b : saved.scratch.records.a; e = find(kind + i);
        if (kind == RB_BACKUP_CONFIG_A && (data[8] != 2 || data[9])) {
            fail(r, RB_BREC_IDENTITY, 1, kind + i, 0, e->lba); return 1;
        }
        if (!equal(data + 48, saved.container.media_id, 16)) {
            fail(r, RB_BREC_IDENTITY, 2, kind + i, 0, e->lba); return 1;
        }
    }
    return 0;
}

void rb_backup_check_records(rb_backup_records *r, rb_sector_reader read,
                              void *opaque, rb_u32 size)
{
    rb_u16 i, j, code, ebrs = 0, boots = 0, found;
    const rb_backup_extent *e;
    const rb_partition *p, *admin = (const rb_partition *)0;
    clear(&saved, sizeof(saved)); fail(r, RB_BREC_OK, 0, 0, 0, 0);
    saved.read = read; saved.opaque = opaque;
    code = rb_backup_validate(&saved.container, read, opaque, size);
    if (code) { fail(r, RB_BREC_CONTAINER, code, 0, 0, 0); return; }
    rb_scan_partitions(&saved.scan, read_table, (void *)0,
        saved.container.capacity_low, saved.container.capacity_high, saved.container.disk_id);
    if (saved.read_status) { read_failure(r); return; }
    if (saved.scan.status) {
        fail(r, RB_BREC_LAYOUT, saved.scan.status, saved.kind, saved.index, saved.scan.error_lba); return;
    }
    if (!equal(saved.scratch.records.mbr + 432, (const rb_u8 *)"RBM1", 4)
            || dword(saved.scratch.records.mbr + 436) != saved.container.admin_start) {
        fail(r, RB_BREC_ADMIN, 0, RB_BACKUP_APPROVED, 0, 0); return;
    }
    for (i = 4; i < saved.scan.count; ++i) {
        p = &saved.scan.entries[i];
        if (p->start == saved.container.admin_start && p->sectors == saved.container.admin_sectors
                && (p->type == 0x16 || p->type == 0x1E)) { admin = p; }
    }
    if (!admin) { fail(r, RB_BREC_ADMIN, 1, 0, 0, saved.container.admin_start); return; }
    if (rb_layout_crc(&saved.scan) != saved.container.layout_crc) {
        fail(r, RB_BREC_IDENTITY, 3, 0, 0, 0); return;
    }
    for (i = 0; i < saved.container.count; ++i) {
        e = &saved.container.entries[i];
        if (e->kind == RB_BACKUP_EBR) {
            if (e->index >= saved.scan.ebr_count || e->lba != saved.scan.ebr_lba[e->index]) {
                fail(r, RB_BREC_COVERAGE, RB_BREC_EBR_SET, e->kind, e->index, e->lba); return;
            }
            ++ebrs;
        } else if (e->kind == RB_BACKUP_BOOT) {
            found = 0;
            for (j = 0; j < saved.scan.count; ++j) {
                p = &saved.scan.entries[j];
                if (data_partition(p) && p->start == e->owner_start && p->sectors == e->owner_sectors) { found = 1; }
            }
            if (!found) { fail(r, RB_BREC_COVERAGE, RB_BREC_BOOT_OWNER, e->kind, e->index, e->lba); return; }
            ++boots;
        }
    }
    for (i = 0; i < saved.scan.count; ++i) {
        p = &saved.scan.entries[i];
        if (!data_partition(p)) { continue; }
        found = 0;
        for (j = 0; j < saved.container.count; ++j) {
            e = &saved.container.entries[j];
            if (e->kind == RB_BACKUP_BOOT && e->lba == p->start && e->owner_start == p->start) { found = 1; }
        }
        if (!found) { fail(r, RB_BREC_COVERAGE, RB_BREC_MISSING_START, RB_BACKUP_BOOT, RB_CONFIG_NONE, p->start); return; }
    }
    if (load_pair(r, RB_BACKUP_CONFIG_A, admin) || load_pair(r, RB_BACKUP_STATE_A, admin)) { return; }
    i = rb_backup_unlinked_profile(&saved.config.config, &saved.state.state);
    if (i != RB_CONFIG_NONE) {
        fail(r, RB_BREC_INSTALLATION, i, RB_BACKUP_CONFIG_A + saved.config.source,
            0, saved.config.config.entries[i].start); return;
    }
    r->partitions = saved.scan.count; r->ebrs = ebrs; r->boot_areas = boots;
    r->config_source = saved.config.source; r->state_source = saved.state.source;
    r->config_generation = saved.config.config.generation; r->state_generation = saved.state.state.generation;
}

rb_backup_saved *rb_backup_open_records(rb_backup_records *r,
    rb_sector_reader read, void *opaque, rb_u32 size)
{
    rb_backup_check_records(r, read, opaque, size);
    return r->status ? (rb_backup_saved *)0 : &saved;
}
