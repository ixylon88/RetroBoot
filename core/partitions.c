#include "partitions.h"

static rb_u32 read32(const rb_u8 *p)
{
    return (rb_u32)p[0] | ((rb_u32)p[1] << 8)
         | ((rb_u32)p[2] << 16) | ((rb_u32)p[3] << 24);
}

static rb_u16 zero_entry(const rb_u8 *p)
{
    rb_u16 i;
    for (i = 0; i < 16; ++i) {
        if (p[i] != 0) { return 0; }
    }
    return 1;
}

static rb_u16 extended(rb_u16 type)
{
    return type == 0x05U || type == 0x0FU;
}

static rb_u16 data_type(rb_u16 type)
{
    /* Reading these types is not filesystem recognition or boot approval. */
    return type == 0x06U || type == 0x16U || type == 0x0EU || type == 0x1EU
        || type == 0x0BU || type == 0x1BU || type == 0x0CU || type == 0x1CU
        || type == 0x07U || type == 0x17U;
}

static rb_u16 fail(rb_partition_scan *r, rb_u16 code, rb_u32 lba, rb_u16 slot)
{
    r->status = code;
    r->error_lba = lba;
    r->error_slot = slot;
    return code;
}

/* Inclusive last LBA permits a valid final sector at FFFFFFFFh. */
static rb_u16 bounds(rb_u32 start, rb_u32 count, rb_u32 low, rb_u32 high)
{
    if (start == 0 || count == 0) { return RB_SCAN_RANGE; }
    if (count - 1 > 0xFFFFFFFFUL - start) { return RB_SCAN_OVERFLOW; }
    if (high == 0 && start + (count - 1) >= low) { return RB_SCAN_RANGE; }
    return RB_SCAN_OK;
}

static rb_u16 overlap(rb_u32 start, rb_u32 count, const rb_partition *p)
{
    return p->sectors != 0 && start <= p->start + (p->sectors - 1)
        && p->start <= start + (count - 1);
}

static void decode(rb_partition *p, const rb_u8 *entry, rb_u32 table,
                   rb_u16 slot, rb_u16 logical)
{
    p->start = read32(entry + 8);
    p->sectors = read32(entry + 12);
    p->table_lba = table;
    p->flag = entry[0];
    p->type = entry[4];
    p->slot = slot;
    p->logical = logical;
}

rb_u16 rb_scan_partitions(rb_partition_scan *r, rb_sector_reader read,
                         void *opaque, rb_u32 low, rb_u32 high, rb_u32 expected_id)
{
    rb_u8 sector[512];
    rb_u8 *bytes = (rb_u8 *)r;
    rb_u16 i, j, code, active = 0, ext_slot = 4;
    rb_u32 base, last, current, relative, next, length;
    rb_partition *p;
    const rb_u8 *entry;
    for (i = 0; i < sizeof(*r); ++i) { bytes[i] = 0; }
    if (low == 0 && high == 0) { return fail(r, RB_SCAN_RANGE, 0, 0); }
    if (read(0, sector, opaque) != 0) { return fail(r, RB_SCAN_IO, 0, 0); }
    if (sector[510] != 0x55 || sector[511] != 0xAA) {
        return fail(r, RB_SCAN_SIGNATURE, 0, 0);
    }
    r->disk_id = read32(sector + 440);
    if (r->disk_id != expected_id) { return fail(r, RB_SCAN_IDENTITY, 0, 0); }
    r->count = 4;
    for (i = 0; i < 4; ++i) {
        entry = sector + 446 + i * 16;
        p = &r->entries[i];
        decode(p, entry, 0, i + 1, 0);
        if (p->type == 0) {
            if (!zero_entry(entry)) { return fail(r, RB_SCAN_EMPTY, 0, i + 1); }
            continue;
        }
        if (p->flag != 0 && p->flag != 0x80U) { return fail(r, RB_SCAN_FLAGS, 0, i + 1); }
        if (extended(p->type)) {
            if (p->flag != 0) { return fail(r, RB_SCAN_FLAGS, 0, i + 1); }
            if (ext_slot != 4) { return fail(r, RB_SCAN_EXTENDED, 0, i + 1); }
            ext_slot = i;
        } else if (!data_type(p->type)) {
            return fail(r, RB_SCAN_TYPE, 0, i + 1);
        }
        if (p->flag != 0 && ++active > 1) { return fail(r, RB_SCAN_FLAGS, 0, i + 1); }
        code = bounds(p->start, p->sectors, low, high);
        if (code != 0) { return fail(r, code, 0, i + 1); }
        for (j = 0; j < i; ++j) {
            if (overlap(p->start, p->sectors, &r->entries[j])) {
                return fail(r, RB_SCAN_OVERLAP, 0, i + 1);
            }
        }
    }
    if (ext_slot == 4) { return RB_SCAN_OK; }
    base = r->entries[ext_slot].start;
    last = base + (r->entries[ext_slot].sectors - 1);
    current = base;
    for (;;) {
        for (i = 0; i < r->ebr_count; ++i) {
            if (current == r->ebr_lba[i]) { return fail(r, RB_SCAN_LOOP, current, 0); }
        }
        if (r->ebr_count == RB_SCAN_EBRS) { return fail(r, RB_SCAN_LIMIT, current, 0); }
        if (current < base || current > last) { return fail(r, RB_SCAN_RANGE, current, 0); }
        for (i = 4; i < r->count; ++i) {
            if (overlap(current, 1, &r->entries[i])) {
                return fail(r, RB_SCAN_OVERLAP, current, 0);
            }
        }
        r->ebr_lba[r->ebr_count++] = current;
        if (read(current, sector, opaque) != 0) { return fail(r, RB_SCAN_IO, current, 0); }
        if (sector[510] != 0x55 || sector[511] != 0xAA) {
            return fail(r, RB_SCAN_SIGNATURE, current, 0);
        }
        for (i = 2; i < 4; ++i) {
            if (!zero_entry(sector + 446 + i * 16)) {
                return fail(r, RB_SCAN_SLOTS, current, i + 1);
            }
        }
        entry = sector + 446;
        if (entry[4] == 0) {
            if (!zero_entry(entry)) { return fail(r, RB_SCAN_EMPTY, current, 1); }
        } else {
            p = &r->entries[r->count];
            decode(p, entry, current, r->count - 3, 1);
            if (p->flag != 0) { return fail(r, RB_SCAN_FLAGS, current, 1); }
            if (!data_type(p->type)) { return fail(r, RB_SCAN_TYPE, current, 1); }
            relative = p->start;
            if (relative > 0xFFFFFFFFUL - current) { return fail(r, RB_SCAN_OVERFLOW, current, 1); }
            p->start = current + relative;
            code = bounds(p->start, p->sectors, low, high);
            if (code != 0) { return fail(r, code, current, 1); }
            if (relative == 0 || p->start < base || p->start + (p->sectors - 1) > last) {
                return fail(r, RB_SCAN_RANGE, current, 1);
            }
            for (i = 4; i < r->count; ++i) {
                if (overlap(p->start, p->sectors, &r->entries[i])) {
                    return fail(r, RB_SCAN_OVERLAP, current, 1);
                }
            }
            for (i = 0; i < r->ebr_count; ++i) {
                if (r->ebr_lba[i] >= p->start && r->ebr_lba[i] <= p->start + (p->sectors - 1)) {
                    return fail(r, RB_SCAN_OVERLAP, current, 1);
                }
            }
            ++r->count;
        }
        entry = sector + 462;
        if (entry[4] == 0) {
            if (!zero_entry(entry)) { return fail(r, RB_SCAN_EMPTY, current, 2); }
            return RB_SCAN_OK;
        }
        if (!extended(entry[4])) { return fail(r, RB_SCAN_TYPE, current, 2); }
        if (entry[0] != 0) { return fail(r, RB_SCAN_FLAGS, current, 2); }
        relative = read32(entry + 8);
        length = read32(entry + 12);
        if (relative > 0xFFFFFFFFUL - base) { return fail(r, RB_SCAN_OVERFLOW, current, 2); }
        next = base + relative;
        code = bounds(next, length, low, high);
        if (code != 0) { return fail(r, code, current, 2); }
        if (next < base || next + (length - 1) > last) { return fail(r, RB_SCAN_RANGE, current, 2); }
        current = next;
    }
}
