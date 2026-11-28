/* Temporary DOS/Win9x installation visibility on the owned reference disk. */
#include "fat_plan.h"
#include "mbr_console.h"
#include "mbr_compare.h"
#include "rescue_text.h"

enum { KEEP, SYSTEM, SHARED, ADMIN };
typedef struct {
    rb_u32 lba;
    rb_u8 roles[4], entries[64];
} install_table;
#include "install_reference.h"

#define TABLES (sizeof(reference) / sizeof(reference[0]))
#define NO_LBA 0xffffffffUL
typedef struct {
    rb_rescue_device disk;
    rb_u16 geometry[3];
    rb_u8 tables[TABLES][512];
} install_snapshot;

static install_snapshot shown, repeated;
static rb_partition_scan scan;
static rb_fat_plan fat;
static rb_u32 error_lba;
static const char *const systems[] = {"MS-DOS 6.22", "Windows 95 OSR2", "Windows 98 SE"};

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
    const install_snapshot *s = (const install_snapshot *)opaque;
    rb_u16 i, b;
    for (i = 0; i < TABLES; ++i) {
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

static const char *observe(install_snapshot *s, rb_u16 os, rb_u16 slot)
{
    static const rb_u32 disk_id = INSTALL_DISK_ID;
    static const rb_u8 boot_offsets[] = {0, 1, 2, 6, 7, 8};
    rb_u8 sector[512];
    const rb_partition *target;
    rb_u16 i, b, status, count;
    error_lba = NO_LBA;
    if (rb_rescue_probe(&s->disk)) { return RB_RS_FP_DEVICE; }
    rb_dos_geometry(s->geometry);
    if (s->geometry[0] == 0 || s->geometry[0] > 1024 || s->geometry[1] != INSTALL_HEADS
            || s->geometry[2] != INSTALL_SPT
            || (rb_u32)s->geometry[0] * INSTALL_HEADS * INSTALL_SPT < INSTALL_END) {
        return RB_RS_IP_GEOMETRY;
    }
    if (s->disk.capacity_high || s->disk.capacity_low < INSTALL_END
            || (s->disk.mode == 1 && s->disk.capacity_low != INSTALL_CAPACITY)) { return RB_RS_IP_DISK; }
    for (i = 0; i < TABLES; ++i) {
        error_lba = reference[i].lba;
        if (rb_disk_read(error_lba, s->tables[i], 0)) { return RB_RS_FP_IO; }
        if (!i && !equal(s->tables[0] + 440, (const rb_u8 *)&disk_id, sizeof(disk_id))) { return RB_RS_IP_DISK; }
        if (!matches_entries(&reference[i], s->tables[i] + 446)) { return RB_RS_IP_LAYOUT; }
    }
    if (rb_scan_partitions(&scan, table_read, s, s->disk.capacity_low, s->disk.capacity_high, INSTALL_DISK_ID)) {
        error_lba = scan.error_lba;
        return RB_RS_IP_LAYOUT;
    }
    error_lba = NO_LBA;
    if (reference[0].roles[slot - 1] != SYSTEM) { return RB_RS_IP_SYSTEM_SLOT; }
    target = &scan.entries[slot - 1];
    status = rb_plan_primary_fat(&fat, target, s->tables[0] + 446 + (slot - 1) * 16,
                                 &s->disk, s->geometry, 0);
    if (status) { return RB_RS_IP_LAYOUT; }
    if (os == 0 && ((target->type & ~0x10U) != 0x06 || target->sectors >= 0x400000UL)) {
        return RB_RS_IP_DOS_FAT;
    }
    count = fat.bits == 16 ? 1 : sizeof(boot_offsets);
    for (i = 0; i < count; ++i) {
        error_lba = target->start + boot_offsets[i];
        if (rb_disk_read(error_lba, sector, 0)) { return RB_RS_FP_IO; }
        for (b = 0; b < sizeof(sector); ++b) {
            if (sector[b]) { return RB_RS_IP_OCCUPIED; }
        }
    }
    error_lba = NO_LBA;
    return 0;
}

static void row(rb_u16 table, rb_u16 entry, rb_u16 offset, rb_u8 old_value, rb_u8 new_value)
{
    rb_putc(table ? 'L' : 'P'); rb_putc('0' + (table ? table : entry + 1));
    print("     "); hex(reference[table].lba, 8);
    print("    "); hex(offset, 4);
    print("    "); hex(old_value, 2); print(" -> "); hex(new_value, 2); line("");
}

static void display(rb_u16 slot)
{
    const rb_partition *target = &scan.entries[slot - 1];
    rb_u16 t, i, role, offset, changed = 0, sectors = 0;
    rb_u8 flag, type;
    print(RB_RS_DISK_ID); rb_putc(' '); hex(scan.disk_id, 8); print("    FAT"); count("", fat.bits);
    print(RB_RS_FP_VOLUME); rb_putc(' '); hex(target->start, 8);
    print(" - "); hex(target->start + target->sectors - 1, 8); line("");
    line(RB_RS_IP_BOOT_CLEAR); line(RB_RS_IP_VIEW); line(RB_RS_IP_COLUMNS);
    for (t = 0; t < TABLES; ++t) {
        rb_u16 previous = changed;
        for (i = 0; i < 4; ++i) {
            role = reference[t].roles[i];
            if (role != SYSTEM && role != SHARED) { continue; }
            offset = 446 + 16 * i;
            flag = (role == SYSTEM && i + 1 == slot) ? 0x80 : 0;
            type = reference[t].entries[16 * i + 4];
            if (!flag) { type |= 0x10; }
            if (shown.tables[t][offset] != flag) {
                row(t, i, offset, shown.tables[t][offset], flag); ++changed;
            }
            if (shown.tables[t][offset + 4] != type) {
                row(t, i, offset + 4, shown.tables[t][offset + 4], type); ++changed;
            }
        }
        if (changed != previous) { ++sectors; }
    }
    count(RB_RS_IP_BYTES " ", changed);
    count(RB_RS_IP_SECTORS " ", sectors);
}

static void blocked(const char *message)
{
    line(message);
    if (error_lba != NO_LBA) { print("LBA "); hex(error_lba, 8); line(""); }
    line("RB INSTALL PLAN BLOCKED");
}

static rb_u16 choose(const char *prompt, rb_u16 first, rb_u16 last)
{
    rb_u16 key;
    line(prompt);
    do { key = rb_console_key(); } while (key != 27 && (key < first || key > last));
    return key;
}

rb_u16 __cdecl rb_install_plan_run(rb_u16 drive)
{
    rb_u16 os, slot;
    const char *error;
    (void)drive;
    line(RB_RS_IP_TITLE); line(RB_RS_IP_SCOPE);
    for (;;) {
        os = choose(RB_RS_IP_OS, '1', '3');
        if (os == 27) { return 0; }
        os -= '1';
        slot = choose(RB_RS_IP_SLOT, '1', '4');
        if (slot == 27) { continue; }
        slot -= '0';
        print(systems[os]); print("  P"); rb_putc('0' + slot); line("");
        error = observe(&shown, os, slot);
        if (error) { blocked(error); continue; }
        display(slot);
        if (choose(RB_RS_IP_REPEAT, 'R', 'R') == 27) { continue; }
        error = observe(&repeated, os, slot);
        if (error || !equal((const rb_u8 *)&shown, (const rb_u8 *)&repeated, sizeof(shown))) {
            blocked(error ? error : RB_RS_IP_CHANGED);
        } else { line("RB INSTALL PLAN VERIFIED"); }
    }
}
