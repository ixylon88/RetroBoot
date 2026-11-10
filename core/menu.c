#include "bios_ui.h"
#include "menu.h"
#include "partitions.h"
#include "stage2.h"

#define NORMAL 0x17U
#define TITLE 0x1FU
#define SELECTED 0x70U

static const char * const labels[3] = {
    "Systeminformationen", "Partitionen", "Recovery-Hinweise"
};
static const char digits[] = "0123456789ABCDEF";
static const char * const scan_errors[] = {
    "OK", "Sektor konnte nicht gelesen werden", "Ungueltige Sektorsignatur",
    "Disk-ID stimmt nicht mit dem Bootvorgang ueberein", "Ungueltige Aktivflags",
    "Partitionstyp wird nicht unterstuetzt", "Leerer Eintrag enthaelt Daten",
    "32-Bit-LBA-Ueberlauf", "Bereich ausserhalb der erlaubten Grenzen",
    "Ueberlappende Daten- oder Tabellenbereiche", "Mehrere erweiterte Partitionen",
    "Zusaetzlicher Eintrag im EBR", "Schleife in der EBR-Kette", "Mehr als 16 EBR-Sektoren"
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
        text(row, 4, "CHS: Koepfe", NORMAL);
        decimal(row, 17, (rb_u16)snapshot->heads);
        text(row, 24, "Sektoren/Spur", NORMAL);
        decimal(row, 40, (rb_u16)snapshot->sectors_per_track);
    } else {
        text(row, 4, "Leseweg: EDD. Keine CHS-Geometrie abgefragt.", NORMAL);
    }
}

static void draw(const rb_menu_state *state, rb_u16 view, const rb_loader_snapshot *snapshot,
                 const rb_partition_scan *scan, rb_u16 page)
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
    text(2, 65, "Nur lesen", 0x1E);
    if (view == 0) {
        text(5, 4, "Startauswahl", TITLE);
        text(6, 4, "Keine Startprofile eingerichtet.", NORMAL);
        text(7, 4, "Automatischer Start: aus", NORMAL);
        for (index = 0; index < 3; ++index) {
            row = 9 + index * 2;
            if (state->selected == index) {
                rb_video_fill(row * 80U + 4, 71, 0x7020);
                text(row, 5, ">", SELECTED);
            }
            text(row, 8, labels[index], state->selected == index ? SELECTED : NORMAL);
        }
        text(17, 4, "BIOS-Laufwerk:", NORMAL);
        hex(17, 19, rb_boot.drive, 2); text(17, 21, "h", NORMAL);
        text(18, 4, rb_boot.io_mode == 1 ? "BIOS-Leseweg: EDD" : "BIOS-Leseweg: CHS", NORMAL);
    } else if (view == 1) {
        text(5, 4, labels[0], TITLE);
        text(7, 4, "BIOS-Laufwerk (hex):", NORMAL); hex(7, 29, rb_boot.drive, 2);
        text(8, 4, "BIOS-Leseweg:", NORMAL);
        text(8, 29, rb_boot.io_mode == 1 ? "EDD" : "CHS", NORMAL);
        text(10, 4, "Erreichbare Sektoren (hex):", NORMAL);
        hex(11, 6, rb_boot.reachable_sectors_high, 8);
        text(11, 14, ":", NORMAL); hex(11, 15, rb_boot.reachable_sectors_low, 8);
        text(13, 4, "Disk-ID (hex):", NORMAL); hex(13, 29, read32(snapshot->mbr + 440), 8);
        geometry(snapshot, 15);
        text(18, 4, "Angaben aus dem Bootvorgang.", NORMAL);
    } else if (view == 2) {
        text(5, 4, "Partitionen: MBR / EBR", TITLE);
        if (scan->status != RB_SCAN_OK) {
            text(8, 4, "Strukturpruefung abgebrochen.", 0x1E);
            text(10, 4, scan_errors[scan->status], 0x1E);
            text(12, 4, "LBA (hex):", NORMAL); hex(12, 23, scan->error_lba, 8);
            text(13, 4, "Eintrag:", NORMAL);
            if (scan->error_slot != 0) { decimal(13, 23, scan->error_slot); }
            else { text(13, 23, "gesamter Sektor", NORMAL); }
            text(16, 4, "Es wurden keine Datentraegerdaten veraendert.", NORMAL);
            text(18, 4, "Esc: zurueck. F2: erneut lesen.", NORMAL);
        } else {
            text(6, 4, "Struktur geprueft; kein OS-Start freigegeben.", NORMAL);
            text(7, 4, "Eintr Flag  Typ    Start-LBA       Sektoren       Tabelle-LBA", TITLE);
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
            text(18, 4, "Seite", NORMAL); decimal(18, 10, page + 1);
            text(18, 12, "/", NORMAL); decimal(18, 14, (scan->count + 7) / 8);
            text(18, 20, "Bild hoch/runter: Blaettern", NORMAL);
        }
        geometry(snapshot, 19);
    } else {
        text(5, 4, labels[2], TITLE);
        text(8, 4, "Wiederherstellung ist noch nicht verfuegbar.", NORMAL);
        text(10, 4, "Die Informationsseiten stehen mit F2 und Esc bereit.", NORMAL);
        text(13, 4, "Es werden keine Datentraegerdaten veraendert.", NORMAL);
    }
    text(21, 4, "Pfeile: Auswahl  Enter: Anzeigen  Esc: Menue", NORMAL);
    text(22, 4, "F2: Partitionen  F8: Recovery-Hinweise", NORMAL);
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
    rb_menu_state state;
    rb_u16 key, action, rescan, view = 0, serial = 0, page = 0;
    rb_u32 now;
    rb_loader_copy(&snapshot);
    /* No configured/approved boot profiles: diagnostic entries, no timer. */
    rb_menu_init(&state, 3, 7, 0, 0, rb_ticks());
    rb_video_init();
    draw(&state, view, &snapshot, &scan, page);
    debug_state(serial, view, state.selected, page);
    debug_text("RB MENU READY\r\n");
    for (;;) {
        key = rb_key_poll();
        now = rb_ticks();
        if (key == RB_KEY_NONE) {
            rb_menu_step(&state, key, now);
            rb_idle();
            continue;
        }
        rescan = 0;
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
        } else if ((key >> 8) == 0x42U) {
            state.selected = 2; view = 3;
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
        }
        draw(&state, view, &snapshot, &scan, page);
        debug_state(++serial, view, state.selected, page);
    }
}
