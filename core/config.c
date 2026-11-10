#include "config.h"

static rb_u16 word(const rb_u8 *p)
{
    return p[0] | ((rb_u16)p[1] << 8);
}

static rb_u32 dword(const rb_u8 *p)
{
    return (rb_u32)word(p) | ((rb_u32)word(p + 2) << 16);
}

static void clear(void *p, rb_u16 length)
{
    rb_u8 *bytes = (rb_u8 *)p;
    while (length != 0) { bytes[--length] = 0; }
}

static rb_u16 zeros(const rb_u8 *p, rb_u16 length)
{
    while (length != 0) { if (p[--length] != 0) { return 0; } }
    return 1;
}

static rb_u32 crc_byte(rb_u32 crc, rb_u8 value)
{
    rb_u16 i;
    crc ^= value;
    for (i = 0; i < 8; ++i) {
        crc = (crc >> 1) ^ ((crc & 1) ? 0xEDB88320UL : 0);
    }
    return crc;
}

static rb_u32 crc_value(rb_u32 crc, rb_u32 value, rb_u16 bytes)
{
    while (bytes-- != 0) { crc = crc_byte(crc, (rb_u8)value); value >>= 8; }
    return crc;
}

rb_u32 rb_crc32(const rb_u8 *data, rb_u16 length)
{
    rb_u32 crc = 0xFFFFFFFFUL;
    while (length-- != 0) { crc = crc_byte(crc, *data++); }
    return crc ^ 0xFFFFFFFFUL;
}

static rb_u16 visible(rb_u16 type)
{
    return type == 0x16 || type == 0x1E || type == 0x1B || type == 0x1C || type == 0x17
           ? type - 0x10 : type;
}

rb_u32 rb_layout_crc(const rb_partition_scan *scan)
{
    rb_u16 i;
    rb_u32 crc = crc_value(0xFFFFFFFFUL, 0x314C4252UL, 4); /* RBL1 */
    const rb_partition *p;
    crc = crc_value(crc, scan->count, 2);
    crc = crc_value(crc, scan->ebr_count, 2);
    for (i = 0; i < scan->ebr_count; ++i) { crc = crc_value(crc, scan->ebr_lba[i], 4); }
    for (i = 0; i < scan->count; ++i) {
        p = &scan->entries[i];
        crc = crc_value(crc, p->start, 4);
        crc = crc_value(crc, p->sectors, 4);
        crc = crc_value(crc, p->table_lba, 4);
        crc = crc_value(crc, visible(p->type), 2);
        crc = crc_value(crc, p->slot, 2);
        crc = crc_value(crc, p->logical, 2);
    }
    return crc ^ 0xFFFFFFFFUL;
}

rb_u16 rb_config_decode(rb_config *r, const rb_u8 *data, rb_u16 length,
                        const rb_partition_scan *scan, const rb_partition *admin)
{
    const rb_u8 magic[8] = {'R','B','C','F','G',0,0,0};
    const rb_u8 *p;
    const rb_partition *target;
    rb_profile *entry;
    rb_u16 i, j, count, version, stride, mask = 0, default_found;
    clear(r, sizeof(*r));
    if (length != 512) { return RB_CONFIG_FORMAT; }
    for (i = 0; i < 8; ++i) { if (data[i] != magic[i]) { return RB_CONFIG_FORMAT; } }
    version = word(data + 8); stride = version == 2 ? 52 : 48;
    if ((version != 1 && version != 2) || word(data + 10) != 64 || dword(data + 12) != 512
            || dword(data + 16) == 0 || word(data + 36) > RB_CONFIG_MAX
            || word(data + 38) > 60 || data[44] > 1 || !zeros(data + 45, version == 2 ? 3 : 19)
            || (version == 2 && zeros(data + 48, 16))
            || !zeros(data + 64 + 8 * stride, 508 - (64 + 8 * stride))) { return RB_CONFIG_FORMAT; }
    if (rb_crc32(data, 508) != dword(data + 508)) { return RB_CONFIG_CRC; }
    if (scan->status != RB_SCAN_OK || scan->count < 4 || scan->count > RB_SCAN_PARTITIONS
            || scan->ebr_count > RB_SCAN_EBRS || !admin->logical
            || (admin->type != 0x16 && admin->type != 0x1E)
            || dword(data + 20) == 0 || dword(data + 20) != scan->disk_id
            || dword(data + 24) != rb_layout_crc(scan)
            || dword(data + 28) != admin->start || dword(data + 32) != admin->sectors) {
        return RB_CONFIG_IDENTITY;
    }
    for (i = 0; i < 4; ++i) {
        j = visible(scan->entries[i].type);
        if (j == 0x06 || j == 0x0E || j == 0x0B || j == 0x0C || j == 0x07) { mask |= 1U << i; }
    }
    count = word(data + 36);
    default_found = dword(data + 40) == 0;
    for (i = 0; i < RB_CONFIG_MAX; ++i) {
        p = data + 64 + i * stride;
        if (i >= count) {
            if (!zeros(p, stride)) { return RB_CONFIG_FORMAT; }
            continue;
        }
        if (dword(p) == 0 || p[12] < 1 || p[12] > 4 || p[14] < 1 || p[14] > 2
                || p[15] > 2 || p[16] > 1 || (p[16] && p[15] != 2)
                || (p[17] & ~mask) || !(p[17] & (1U << (p[12] - 1)))
                || (p[14] == 1 && (p[17] != (1U << (p[12] - 1)) || p[13] == 7))
                || p[18] < 1 || p[18] > 24 || p[19] != 0
                || (version == 1 && !zeros(p + 44, 4))
                || (version == 2 && p[16] && zeros(p + 44, 8))) {
            return RB_CONFIG_PROFILE;
        }
        target = &scan->entries[p[12] - 1];
        if (p[13] != visible(target->type) || dword(p + 4) != target->start
                || dword(p + 8) != target->sectors) { return RB_CONFIG_PROFILE; }
        for (j = 0; j < 24; ++j) {
            if (j < p[18] ? p[20 + j] < 32 || p[20 + j] == 127 : p[20 + j] != 0) {
                return RB_CONFIG_PROFILE;
            }
        }
        for (j = 0; j < i; ++j) {
            if (dword(p) == dword(data + 64 + j * stride)) { return RB_CONFIG_PROFILE; }
        }
        if (dword(p) == dword(data + 40)) { default_found = 1; }
    }
    if (!default_found) { return RB_CONFIG_PROFILE; }
    r->generation = dword(data + 16); r->disk_id = dword(data + 20);
    r->layout_crc = dword(data + 24); r->default_id = dword(data + 40);
    r->count = count; r->countdown = word(data + 38); r->language = data[44];
    r->version = version;
    if (version == 2) { for (i = 0; i < 16; ++i) { r->media_id[i] = data[48 + i]; } }
    for (i = 0; i < count; ++i) {
        p = data + 64 + i * stride; entry = &r->entries[i];
        entry->id = dword(p); entry->start = dword(p + 4); entry->sectors = dword(p + 8);
        entry->slot = p[12]; entry->type = p[13]; entry->kind = p[14];
        entry->installed = p[15]; entry->approved = p[16]; entry->visible_mask = p[17];
        if (version == 2) { entry->install_low = dword(p + 44); entry->install_high = dword(p + 48); }
        for (j = 0; j < p[18]; ++j) { entry->name[j] = p[20 + j]; }
    }
    return RB_CONFIG_OK;
}

void rb_config_select(rb_config_result *r, const rb_u8 *a, const rb_u8 *b,
                      rb_u16 readable_mask, const rb_partition_scan *scan,
                      const rb_partition *admin)
{
    rb_config candidate;
    rb_u32 generations[2];
    rb_u16 i;
    clear(r, sizeof(*r)); r->source = RB_CONFIG_NONE;
    r->copies[0] = readable_mask & 1 ? rb_config_decode(&candidate, a, 512, scan, admin) : RB_CONFIG_MISSING;
    generations[0] = r->copies[0] == 0 ? candidate.generation : 0;
    r->copies[1] = readable_mask & 2 ? rb_config_decode(&candidate, b, 512, scan, admin) : RB_CONFIG_MISSING;
    generations[1] = r->copies[1] == 0 ? candidate.generation : 0;
    if (!generations[0] && !generations[1]) {
        r->status = r->copies[0] == RB_CONFIG_MISSING ? r->copies[1] : r->copies[0]; return;
    }
    if (generations[0] == generations[1]) {
        for (i = 0; i < 512; ++i) {
            if (a[i] != b[i]) { r->status = RB_CONFIG_CONFLICT; return; }
        }
    }
    r->source = generations[1] > generations[0] ? 1 : 0;
    rb_config_decode(&r->config, r->source ? b : a, 512, scan, admin);
}
