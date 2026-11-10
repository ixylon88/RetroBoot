#include "bios_ui.h"
#include "menu.h"
#include "partitions.h"
#include "stage2.h"
#include "ui_text.h"
#include "volume.h"

#define NORMAL 0x17U
#define TITLE 0x1FU
#define SELECTED 0x70U

static const char * const labels[3] = {
    RB_UI_SYSTEM_INFO, RB_UI_PARTITIONS, RB_UI_RECOVERY
};
static const char digits[] = "0123456789ABCDEF";
static const char * const scan_errors[] = {
    RB_UI_ERROR_OK, RB_UI_ERROR_IO, RB_UI_ERROR_SIGNATURE,
    RB_UI_ERROR_IDENTITY, RB_UI_ERROR_FLAGS,
    RB_UI_ERROR_TYPE, RB_UI_ERROR_EMPTY,
    RB_UI_ERROR_OVERFLOW, RB_UI_ERROR_RANGE,
    RB_UI_ERROR_OVERLAP, RB_UI_ERROR_EXTENDED,
    RB_UI_ERROR_SLOTS, RB_UI_ERROR_LOOP, RB_UI_ERROR_LIMIT
};
static const char * const volume_messages[] = {
    RB_UI_VOLUME_OK, RB_UI_VOLUME_IO, RB_UI_VOLUME_SIGNATURE, RB_UI_VOLUME_JUMP,
    RB_UI_VOLUME_SECTOR, RB_UI_VOLUME_CLUSTER, RB_UI_VOLUME_RESERVED, RB_UI_VOLUME_FATS,
    RB_UI_VOLUME_ROOT, RB_UI_VOLUME_TOTAL, RB_UI_VOLUME_HIDDEN, RB_UI_VOLUME_LAYOUT,
    RB_UI_VOLUME_TYPE, RB_UI_VOLUME_FAT_SIZE, RB_UI_VOLUME_FAT32, RB_UI_VOLUME_RANGE,
    RB_UI_VOLUME_UNSUPPORTED, RB_UI_VOLUME_MEDIA
};

static void text(rb_u16 row, rb_u16 column, const char *value, rb_u16 color)
{
    rb_video_text(row * 80U + column, value, color);
}

static void cell(rb_u16 row, rb_u16 column, rb_u16 character)
{
    rb_video_fill(row * 80U + column, 1, (NORMAL << 8) | character);
}

static void hex(rb_u16 row, rb_u16 column, rb_u32 value, rb_u16 width)
{
    char buffer[9];
    rb_u16 index = width;
    buffer[index] = 0;
    while (index != 0) {
        buffer[--index] = digits[(rb_u16)value & 15U];
        value >>= 4;
    }
    text(row, column, buffer, NORMAL);
}

static void decimal(rb_u16 row, rb_u16 column, rb_u16 value)
{
    char buffer[6];
    rb_u16 index = 5;
    buffer[index] = 0;
    do {
        buffer[--index] = (char)('0' + value % 10U);
        value /= 10U;
    } while (value != 0);
    text(row, column, buffer + index, NORMAL);
}

static rb_u32 read32(const rb_u8 *bytes)
{
    return (rb_u32)bytes[0] | ((rb_u32)bytes[1] << 8)
         | ((rb_u32)bytes[2] << 16) | ((rb_u32)bytes[3] << 24);
}

static void geometry(const rb_loader_snapshot *snapshot, rb_u16 row)
{
    if (rb_boot.io_mode == 0) {
        text(row, 4, RB_UI_CHS_HEADS, NORMAL);
        decimal(row, 17, (rb_u16)snapshot->heads);
        text(row, 24, RB_UI_CHS_SECTORS, NORMAL);
        decimal(row, 40, (rb_u16)snapshot->sectors_per_track);
    } else {
        text(row, 4, RB_UI_EDD_GEOMETRY, NORMAL);
    }
}

static void draw(const rb_menu_state *state, rb_u16 view, const rb_loader_snapshot *snapshot,
                 const rb_partition_scan *scan, rb_u16 page,
                 const rb_volume_probe *volume, rb_u16 volume_index)
{
    rb_u16 row, index;
    const rb_partition *p;
    rb_video_fill(0, 2000, 0x1720);
    for (row = 2; row < 23; ++row) {
        cell(row, 1, 0xB3); cell(row, 78, 0xB3);
    }
    rb_video_fill(82, 76, 0x17C4);
    rb_video_fill(1842, 76, 0x17C4);
    rb_video_fill(322, 76, 0x17C4);
    cell(1, 1, 0xDA); cell(1, 78, 0xBF);
    cell(23, 1, 0xC0); cell(23, 78, 0xD9);
    text(2, 4, "RetroBoot", TITLE);
    text(2, 65, RB_UI_READ_ONLY, 0x1E);
    if (view == 0) {
        text(5, 4, RB_UI_BOOT_MENU, TITLE);
        text(6, 4, RB_UI_NO_PROFILES, NORMAL);
        text(7, 4, RB_UI_AUTO_OFF, NORMAL);
        for (index = 0; index < 3; ++index) {
            row = 9 + index * 2;
            if (state->selected == index) {
                rb_video_fill(row * 80U + 4, 71, 0x7020);
                text(row, 5, ">", SELECTED);
            }
            text(row, 8, labels[index], state->selected == index ? SELECTED : NORMAL);
        }
        text(17, 4, RB_UI_DRIVE, NORMAL);
        hex(17, 19, rb_boot.drive, 2); text(17, 21, "h", NORMAL);
        text(18, 4, rb_boot.io_mode == 1 ? RB_UI_ROUTE_EDD : RB_UI_ROUTE_CHS, NORMAL);
    } else if (view == 1) {
        text(5, 4, labels[0], TITLE);
        text(7, 4, RB_UI_DRIVE_HEX, NORMAL); hex(7, 29, rb_boot.drive, 2);
        text(8, 4, RB_UI_ROUTE, NORMAL);
        text(8, 29, rb_boot.io_mode == 1 ? "EDD" : "CHS", NORMAL);
        text(10, 4, RB_UI_REACHABLE, NORMAL);
        hex(11, 6, rb_boot.reachable_sectors_high, 8);
        text(11, 14, ":", NORMAL); hex(11, 15, rb_boot.reachable_sectors_low, 8);
        text(13, 4, RB_UI_DISK_ID, NORMAL); hex(13, 29, read32(snapshot->mbr + 440), 8);
        geometry(snapshot, 15);
        text(18, 4, RB_UI_BOOT_SNAPSHOT, NORMAL);
    } else if (view == 2) {
        text(5, 4, RB_UI_PARTITION_TITLE, TITLE);
        if (scan->status != RB_SCAN_OK) {
            text(8, 4, RB_UI_SCAN_FAILED, 0x1E);
            text(10, 4, scan_errors[scan->status], 0x1E);
            text(12, 4, RB_UI_LBA_HEX, NORMAL); hex(12, 23, scan->error_lba, 8);
            text(13, 4, RB_UI_ENTRY, NORMAL);
            if (scan->error_slot != 0) { decimal(13, 23, scan->error_slot); }
            else { text(13, 23, RB_UI_WHOLE_SECTOR, NORMAL); }
            text(16, 4, RB_UI_NO_CHANGES, NORMAL);
            text(18, 4, RB_UI_SCAN_HELP, NORMAL);
        } else {
            text(6, 4, RB_UI_SCAN_OK, NORMAL);
            text(7, 4, RB_UI_TABLE_HEADER, TITLE);
            for (index = page * 8; index < scan->count && index < page * 8 + 8; ++index) {
                row = 9 + index - page * 8;
                p = &scan->entries[index];
                text(row, 4, p->logical ? "L" : "P", NORMAL);
                decimal(row, 5, p->slot);
                hex(row, 10, p->flag, 2);
                hex(row, 16, p->type, 2);
                hex(row, 23, p->start, 8);
                hex(row, 39, p->sectors, 8);
                hex(row, 54, p->table_lba, 8);
            }
            text(18, 4, RB_UI_PAGE, NORMAL); decimal(18, 10, page + 1);
            text(18, 12, "/", NORMAL); decimal(18, 14, (scan->count + 7) / 8);
            text(18, 20, RB_UI_PAGING, NORMAL);
        }
        geometry(snapshot, 19);
    } else if (view == 4) {
        text(5, 4, RB_UI_VOLUME_TITLE, TITLE);
        text(6, 4, RB_UI_VOLUME_SCOPE, NORMAL);
        if (volume_index == RB_MENU_NONE) {
            text(8, 4, RB_UI_VOLUME_NONE, NORMAL);
        } else {
            p = &scan->entries[volume_index];
            text(8, 4, RB_UI_VOLUME_ENTRY, NORMAL);
            text(8, 29, p->logical ? "L" : "P", NORMAL); decimal(8, 30, p->slot);
            text(8, 45, RB_UI_VOLUME_PTYPE, NORMAL); hex(8, 54, p->type, 2);
            text(9, 4, RB_UI_VOLUME_LBA, NORMAL); hex(9, 29, p->start, 8);
            text(11, 4, volume_messages[volume->status], volume->status == 0 ? NORMAL : 0x1E);
            if (volume->status == RB_VOLUME_OK) {
                text(13, 4, RB_UI_VOLUME_KIND, NORMAL);
                text(13, 29, "FAT", NORMAL); decimal(13, 32, volume->fat_bits);
                text(14, 4, RB_UI_VOLUME_BYTES, NORMAL); decimal(14, 29, volume->cluster_bytes);
                text(15, 4, RB_UI_VOLUME_TOTAL_LABEL, NORMAL); hex(15, 29, volume->total_sectors, 8);
                text(16, 4, RB_UI_VOLUME_CLUSTERS, NORMAL); hex(16, 29, volume->clusters, 8);
                text(17, 4, RB_UI_VOLUME_DATA, NORMAL); hex(17, 29, volume->data_lba, 8);
            }
        }
        text(19, 4, RB_UI_VOLUME_HELP, NORMAL);
    } else {
        text(5, 4, labels[2], TITLE);
        text(8, 4, RB_UI_RECOVERY_MISSING, NORMAL);
        text(10, 4, RB_UI_RECOVERY_PAGES, NORMAL);
        text(13, 4, RB_UI_RECOVERY_READ_ONLY, NORMAL);
    }
    text(21, 4, RB_UI_KEY_HELP, NORMAL);
    text(22, 4, RB_UI_FUNCTION_HELP, NORMAL);
}

/* Skip empty primary slots and extended containers; bound every search. */
static rb_u16 next_volume(const rb_partition_scan *scan, rb_u16 index, rb_u16 backwards)
{
    rb_u16 attempts, type;
    if (scan->status != RB_SCAN_OK || scan->count == 0 || scan->count > RB_SCAN_PARTITIONS) {
        return RB_MENU_NONE;
    }
    if (index >= scan->count) { index = backwards ? 0 : scan->count - 1; }
    for (attempts = 0; attempts < scan->count; ++attempts) {
        index = backwards ? (index == 0 ? scan->count - 1 : index - 1)
                          : (index + 1 == scan->count ? 0 : index + 1);
        type = scan->entries[index].type;
        if (type != 0 && type != 0x05U && type != 0x0FU) { return index; }
    }
    return RB_MENU_NONE;
}

static void debug_text(const char *value)
{
    while (*value != 0) {
        rb_debug_putc((rb_u8)*value++);
    }
}

static void debug_hex(rb_u16 value)
{
    rb_u16 shift = 12;
    for (;;) {
        rb_debug_putc(digits[(value >> shift) & 15U]);
        if (shift == 0) { break; }
        shift -= 4;
    }
}

static void debug_state(rb_u16 serial, rb_u16 view, rb_u16 selected, rb_u16 page)
{
    debug_text("RB MENU "); debug_hex(serial);
    debug_text(" view="); debug_hex(view);
    debug_text(" selected="); debug_hex(selected);
    debug_text(" page="); debug_hex(page);
    debug_text("\r\n");
}

void __cdecl rb_menu_run(void)
{
    rb_loader_snapshot snapshot;
    rb_partition_scan scan;
    rb_volume_probe volume;
    rb_menu_state state;
    rb_u16 key, action, rescan, view = 0, serial = 0, page = 0;
    rb_u16 probe, volume_index = RB_MENU_NONE;
    rb_u32 now;
    rb_loader_copy(&snapshot);
    /* No configured/approved boot profiles: diagnostic entries, no timer. */
    rb_menu_init(&state, 3, 7, 0, 0, rb_ticks());
    rb_video_init();
    draw(&state, view, &snapshot, &scan, page, &volume, volume_index);
    debug_state(serial, view, state.selected, page);
    debug_text("RB UI " RB_UI_LANGUAGE " CP437\r\n");
    debug_text("RB MENU READY\r\n");
    for (;;) {
        key = rb_key_poll();
        now = rb_ticks();
        if (key == RB_KEY_NONE) {
            rb_menu_step(&state, key, now);
            rb_idle();
            continue;
        }
        rescan = 0; probe = 0;
        if (view == 0) {
            action = rb_menu_step(&state, key, now);
            if (action != RB_MENU_NONE) { view = action + 1; rescan = view == 2; }
        } else {
            state.remaining_ticks = 0;
        }
        if ((key & 0xFFU) == 27U) {
            view = 0;
        } else if ((key >> 8) == 0x3CU) {
            state.selected = 1; view = 2; rescan = 1;
        } else if ((key >> 8) == 0x3DU) {
            if (view != 4) { volume_index = RB_MENU_NONE; }
            state.selected = 1; view = 2; rescan = 2;
        } else if ((key >> 8) == 0x42U) {
            state.selected = 2; view = 3;
        } else if (view == 4 && ((key >> 8) == 0x4BU || (key >> 8) == 0x4DU)) {
            volume_index = next_volume(&scan, volume_index, (key >> 8) == 0x4BU);
            probe = 1;
        } else if (view == 2 && !rescan && scan.status == RB_SCAN_OK) {
            if ((key >> 8) == 0x49U && page != 0) { --page; }
            if ((key >> 8) == 0x51U && (page + 1) * 8 < scan.count) { ++page; }
        }
        if (view != 2) { page = 0; }
        if (rescan) {
            page = 0;
            debug_text("RB SCAN BEGIN\r\n");
            rb_scan_partitions(&scan, rb_disk_read, (void *)0,
                rb_boot.reachable_sectors_low, rb_boot.reachable_sectors_high,
                read32(snapshot.mbr + 440));
            debug_text("RB SCAN status="); debug_hex(scan.status);
            debug_text(" count="); debug_hex(scan.count);
            debug_text(" ebr="); debug_hex(scan.ebr_count);
            debug_text(" lba="); debug_hex((rb_u16)(scan.error_lba >> 16)); debug_hex((rb_u16)scan.error_lba);
            debug_text(" slot="); debug_hex(scan.error_slot); debug_text("\r\n");
            if (rescan == 2 && scan.status == RB_SCAN_OK) {
                view = 4; probe = 1;
                if (volume_index >= scan.count || scan.entries[volume_index].type == 0
                        || scan.entries[volume_index].type == 0x05U || scan.entries[volume_index].type == 0x0FU) {
                    volume_index = next_volume(&scan, RB_MENU_NONE, 0);
                }
            }
        }
        if (probe && volume_index != RB_MENU_NONE) {
            rb_probe_volume(&volume, &scan.entries[volume_index], rb_disk_read, (void *)0,
                            rb_boot.reachable_sectors_low, rb_boot.reachable_sectors_high);
            debug_text("RB VOLUME index="); debug_hex(volume_index);
            debug_text(" status="); debug_hex(volume.status);
            debug_text(" lba="); debug_hex((rb_u16)(scan.entries[volume_index].start >> 16));
            debug_hex((rb_u16)scan.entries[volume_index].start);
            debug_text(" fat="); debug_hex(volume.fat_bits); debug_text("\r\n");
        } else if (probe) {
            debug_text("RB VOLUME EMPTY\r\n");
        }
        draw(&state, view, &snapshot, &scan, page, &volume, volume_index);
        debug_state(++serial, view, state.selected, page);
    }
}
