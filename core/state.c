#include "state.h"
#include "record_io.h"

static rb_u16 word(const rb_u8 *p) { return p[0] | ((rb_u16)p[1] << 8); }
static rb_u32 dword(const rb_u8 *p) { return (rb_u32)word(p) | ((rb_u32)word(p + 2) << 16); }
static rb_u16 zeros(const rb_u8 *p, rb_u16 n)
{
    while (n) { if (p[--n]) { return 0; } } return 1;
}
static void clear(void *p, rb_u16 n)
{
    rb_u8 *bytes = (rb_u8 *)p;
    while (n) { bytes[--n] = 0; }
}
static rb_u16 visible(rb_u16 type)
{
    return type == 0x16 || type == 0x1E || type == 0x1B || type == 0x1C || type == 0x17 ? type - 0x10 : type;
}

rb_u16 rb_state_decode(rb_install_state *r, const rb_u8 *data, rb_u16 length,
                       const rb_partition_scan *scan, const rb_partition *admin)
{
    const rb_u8 magic[8] = {'R','B','S','T','A','T','E',0};
    const rb_u8 *p, *other;
    const rb_partition *target;
    rb_installation *entry;
    rb_u16 i, j, count;
    clear(r, sizeof(*r));
    if (length != 512) { return RB_CONFIG_FORMAT; }
    for (i = 0; i < 8; ++i) { if (data[i] != magic[i]) { return RB_CONFIG_FORMAT; } }
    if (word(data + 8) != 1 || word(data + 10) != 64 || dword(data + 12) != 512
            || !dword(data + 16) || word(data + 36) > 4 || !zeros(data + 38, 10)
            || zeros(data + 48, 16) || !zeros(data + 320, 188)) { return RB_CONFIG_FORMAT; }
    if (rb_crc32(data, 508) != dword(data + 508)) { return RB_CONFIG_CRC; }
    if (scan->status || scan->count < 4 || scan->count > RB_SCAN_PARTITIONS
            || scan->ebr_count > RB_SCAN_EBRS || !admin->logical
            || (admin->type != 0x16 && admin->type != 0x1E) || !dword(data + 20)
            || dword(data + 20) != scan->disk_id || dword(data + 24) != rb_layout_crc(scan)
            || dword(data + 28) != admin->start || dword(data + 32) != admin->sectors) { return RB_CONFIG_IDENTITY; }
    count = word(data + 36);
    for (i = 0; i < 4; ++i) {
        p = data + 64 + i * 64;
        if (i >= count) { if (!zeros(p, 64)) { return RB_CONFIG_FORMAT; } continue; }
        if (zeros(p, 8) || p[16] < 1 || p[16] > 4 || p[18] < 1 || p[18] > 2
                || p[19] < RB_INSTALL_PLANNED || p[19] > RB_INSTALL_RECOVERY
                || (p[17] != 6 && p[17] != 14 && p[17] != 11 && p[17] != 12 && p[17] != 7)
                || (p[18] == 1 && p[17] == 7) || (p[19] != RB_INSTALL_READY && dword(p + 20))
                || !zeros(p + 24, 40)) { return RB_CONFIG_PROFILE; }
        target = &scan->entries[p[16] - 1];
        if (p[17] != visible(target->type) || dword(p + 8) != target->start
                || dword(p + 12) != target->sectors) { return RB_CONFIG_PROFILE; }
        for (j = 0; j < i; ++j) {
            other = data + 64 + j * 64;
            if (p[16] == other[16] || (dword(p) == dword(other) && dword(p + 4) == dword(other + 4))) {
                return RB_CONFIG_PROFILE;
            }
        }
    }
    r->generation = dword(data + 16); r->disk_id = dword(data + 20); r->layout_crc = dword(data + 24);
    r->count = count;
    for (i = 0; i < 16; ++i) { r->media_id[i] = data[48 + i]; }
    for (i = 0; i < count; ++i) {
        p = data + 64 + i * 64; entry = &r->entries[i];
        entry->install_low = dword(p); entry->install_high = dword(p + 4);
        entry->start = dword(p + 8); entry->sectors = dword(p + 12);
        entry->slot = p[16]; entry->type = p[17]; entry->kind = p[18]; entry->phase = p[19];
        entry->vbr_crc = dword(p + 20);
    }
    return RB_CONFIG_OK;
}

void rb_state_select(rb_state_result *r, const rb_u8 *a, const rb_u8 *b,
                     rb_u16 mask, const rb_partition_scan *scan, const rb_partition *admin)
{
    rb_install_state candidate;
    rb_u32 generations[2];
    rb_u16 i;
    clear(r, sizeof(*r)); r->source = RB_CONFIG_NONE;
    r->copies[0] = mask & 1 ? rb_state_decode(&candidate, a, 512, scan, admin) : RB_CONFIG_MISSING;
    generations[0] = r->copies[0] ? 0 : candidate.generation;
    r->copies[1] = mask & 2 ? rb_state_decode(&candidate, b, 512, scan, admin) : RB_CONFIG_MISSING;
    generations[1] = r->copies[1] ? 0 : candidate.generation;
    if (!generations[0] && !generations[1]) {
        r->status = r->copies[0] == RB_CONFIG_MISSING ? r->copies[1] : r->copies[0]; return;
    }
    if (generations[0] == generations[1]) {
        for (i = 0; i < 512; ++i) { if (a[i] != b[i]) { r->status = RB_CONFIG_CONFLICT; return; } }
    }
    r->source = generations[1] > generations[0] ? 1 : 0;
    rb_state_decode(&r->state, r->source ? b : a, 512, scan, admin);
}

void rb_state_load(rb_state_result *r, rb_sector_reader read, void *opaque,
                   rb_u32 low, rb_u32 high, rb_u32 disk_id, rb_u32 admin_lba)
{
    rb_record_files files;
    rb_u16 i;
    rb_record_read(&files, RB_FILES_STATE, read, opaque, low, high, disk_id, admin_lba);
    rb_state_select(r, files.records[0], files.records[1], files.status ? 0 : files.mask, &files.scan, &files.admin);
    if (files.status) {
        r->status = files.status; r->detail = files.detail; r->error_lba = files.error_lba;
        r->copies[0] = r->copies[1] = files.status; return;
    }
    if (r->status && r->status != RB_CONFIG_CONFLICT && r->status != RB_CONFIG_MISSING) {
        r->error_lba = files.file_lba[r->copies[0] == r->status ? 0 : 1];
    }
    for (i = 0; i < 2; ++i) {
        if (files.copies[i] == RB_CONFIG_IO) {
            r->copies[i] = RB_CONFIG_IO; r->error_lba = files.error_lba;
            if (r->source == RB_CONFIG_NONE) { r->status = RB_CONFIG_IO; }
        }
    }
}
