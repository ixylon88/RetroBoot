/* Temporary DOS/Win9x installation visibility on the owned reference disk. */
#include "install_layout.h"
#include "mbr_console.h"
#include "mbr_compare.h"
#include "rescue_text.h"

enum { KEEP, SYSTEM, SHARED, ADMIN };
typedef struct {
    rb_u32 lba;
    rb_u8 roles[4], entries[64];
} install_table;
#include "install_reference.h"

typedef char table_count_check[(sizeof(reference) / sizeof(reference[0]) == RB_INSTALL_TABLES) ? 1 : -1];
static rb_partition_scan scan;
static rb_fat_plan fat;
const rb_u32 rb_install_capacity = INSTALL_CAPACITY;
const char *const rb_install_systems[] = {"MS-DOS 6.22", "Windows 95 OSR2", "Windows 98 SE"};

rb_u32 rb_install_table_lba(rb_u16 table)
{
    return reference[table].lba;
}

static void hex(rb_u32 value, rb_u16 digits)
{
    static const char alphabet[] = "0123456789ABCDEF";
    print("0x");
    while (digits) { rb_putc(alphabet[(value >> (4 * --digits)) & 15]); }
}

/* The partition walker only sees the sectors captured for this review.
   An unexpected link can never send the BIOS reader to another address. */
static rb_u16 __cdecl table_read(rb_u32 lba, rb_u8 *out, void *opaque)
{
    const rb_install_snapshot *s = (const rb_install_snapshot *)opaque;
    rb_u16 i, b;
    for (i = 0; i < RB_INSTALL_TABLES; ++i) {
        if (lba != reference[i].lba) { continue; }
        for (b = 0; b < 512; ++b) { out[b] = s->tables[i][b]; }
        return 0;
    }
    return 1;
}

static int matches_entries(const install_table *t, const rb_u8 *actual)
{
    rb_u16 i, b, role;
    for (i = 0; i < 4; ++i) {
        const rb_u8 *entry = actual + 16 * i;
        const rb_u8 *expected = t->entries + 16 * i;
        role = t->roles[i];
        for (b = 0; b < 16; ++b) {
            if (b == 0 && role == SYSTEM) { continue; } /* scanner validates active flags */
            if (b == 4 && (role == SYSTEM || role == SHARED) && entry[b] == (expected[b] | 0x10U)) {
                continue;
            }
            if (entry[b] != expected[b]) { return 0; }
        }
    }
    return 1;
}

const char *rb_install_observe(rb_install_snapshot *s, rb_u16 os, rb_u16 slot)
{
    static const rb_u32 disk_id = INSTALL_DISK_ID;
    const rb_partition *target;
    rb_u16 i, status;
    s->error_lba = RB_INSTALL_NO_LBA;
    if (rb_rescue_probe(&s->disk)) { return RB_RS_FP_DEVICE; }
    rb_dos_geometry(s->geometry);
    if (s->geometry[0] == 0 || s->geometry[0] > 1024 || s->geometry[1] != INSTALL_HEADS
            || s->geometry[2] != INSTALL_SPT
            || (rb_u32)s->geometry[0] * INSTALL_HEADS * INSTALL_SPT < INSTALL_END) {
        return RB_RS_IP_GEOMETRY;
    }
    if (s->disk.capacity_high || s->disk.capacity_low < INSTALL_END
            || (s->disk.mode == 1 && s->disk.capacity_low != INSTALL_CAPACITY)) { return RB_RS_IP_DISK; }
    for (i = 0; i < RB_INSTALL_TABLES; ++i) {
        s->error_lba = reference[i].lba;
        if (rb_disk_read(s->error_lba, s->tables[i], 0)) { return RB_RS_FP_IO; }
        if (!i && !equal(s->tables[0] + 440, (const rb_u8 *)&disk_id, sizeof(disk_id))) { return RB_RS_IP_DISK; }
        if (!matches_entries(&reference[i], s->tables[i] + 446)) { return RB_RS_IP_LAYOUT; }
    }
    if (rb_scan_partitions(&scan, table_read, s, s->disk.capacity_low, s->disk.capacity_high, INSTALL_DISK_ID)) {
        s->error_lba = scan.error_lba;
        return RB_RS_IP_LAYOUT;
    }
    s->error_lba = RB_INSTALL_NO_LBA;
    if (slot < 1 || slot > 4 || reference[0].roles[slot - 1] != SYSTEM) { return RB_RS_IP_SYSTEM_SLOT; }
    target = &scan.entries[slot - 1];
    status = rb_plan_primary_fat(&fat, target, s->tables[0] + 446 + (slot - 1) * 16,
                                 &s->disk, s->geometry, 0);
    if (status) { return RB_RS_IP_LAYOUT; }
    if (os == 0 && ((target->type & ~0x10U) != 0x06 || target->sectors >= 0x400000UL)) {
        return RB_RS_IP_DOS_FAT;
    }
    s->bits = fat.bits;
    s->start = target->start;
    s->end = s->start + target->sectors - 1;
    return 0;
}

const char *rb_install_empty_boot(rb_install_snapshot *s, rb_sector_reader read)
{
    static const rb_u8 boot_offsets[] = {0, 1, 2, 6, 7, 8};
    rb_u8 sector[512];
    rb_u16 i, b, count = s->bits == 16 ? 1 : sizeof(boot_offsets);
    for (i = 0; i < count; ++i) {
        s->error_lba = s->start + boot_offsets[i];
        if (read(s->error_lba, sector, 0)) { return RB_RS_FP_IO; }
        for (b = 0; b < sizeof(sector); ++b) {
            if (sector[b]) { return RB_RS_IP_OCCUPIED; }
        }
    }
    s->error_lba = RB_INSTALL_NO_LBA;
    return 0;
}

static void row(rb_u16 table, rb_u16 entry, rb_u16 offset, rb_u8 old_value, rb_u8 new_value)
{
    rb_putc(table ? 'L' : 'P'); rb_putc('0' + (table ? table : entry + 1));
    print("     "); hex(reference[table].lba, 8);
    print("    "); hex(offset, 4);
    print("    "); hex(old_value, 2); print(" -> "); hex(new_value, 2); line("");
}

void rb_install_render(rb_install_tables out, const rb_install_tables in, rb_u16 slot)
{
    rb_u16 t, i, b;
    for (t = 0; t < RB_INSTALL_TABLES; ++t) {
        for (b = 0; b < 512; ++b) { out[t][b] = in[t][b]; }
        for (i = 0; i < 4; ++i) {
            rb_u16 role = reference[t].roles[i], offset = 446 + 16 * i;
            int target = role == SYSTEM && i + 1 == slot;
            if (role == SYSTEM || role == SHARED) {
                out[t][offset] = target ? 0x80 : 0;
                out[t][offset + 4] = reference[t].entries[16 * i + 4] | (target ? 0 : 0x10);
            }
        }
    }
}

void rb_install_target(const rb_install_snapshot *s)
{
    print(RB_RS_DISK_ID); rb_putc(' '); hex(INSTALL_DISK_ID, 8); print("    FAT"); count("", s->bits);
    print(RB_RS_FP_VOLUME); rb_putc(' '); hex(s->start, 8);
    print(" - "); hex(s->end, 8); line("");
}

void rb_install_changes(const rb_install_tables from, const rb_install_tables to)
{
    rb_u16 t, i, offset, changed = 0, sectors = 0;
    line(RB_RS_IP_COLUMNS);
    for (t = 0; t < RB_INSTALL_TABLES; ++t) {
        rb_u16 previous = changed;
        for (i = 0; i < 4; ++i) {
            for (offset = 446 + 16 * i; offset <= 450 + 16 * i; offset += 4) {
                if (from[t][offset] != to[t][offset]) {
                    row(t, i, offset, from[t][offset], to[t][offset]);
                    ++changed;
                }
            }
        }
        if (previous != changed) { ++sectors; }
    }
    count(RB_RS_IP_BYTES " ", changed);
    count(RB_RS_IP_SECTORS " ", sectors);
}

void rb_install_error(const char *message, rb_u32 lba)
{
    line(message);
    if (lba != RB_INSTALL_NO_LBA) { print("LBA "); hex(lba, 8); line(""); }
}
