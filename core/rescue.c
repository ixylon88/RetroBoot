#include "rescue.h"
#include "rescue_file.h"
#include "rescue_match.h"
#include "bios_ui.h"
#include "rescue_text.h"

static const char digits[] = "0123456789ABCDEF";
static const char * const reasons[] = {
    RB_RS_OK, RB_RS_NO_DISK, RB_RS_PARAMS, RB_RS_GEOMETRY, RB_RS_IO, RB_RS_CHANGED
};

static void clear(void *p, rb_u16 size)
{
    rb_u8 *bytes = (rb_u8 *)p;
    while (size) { bytes[--size] = 0; }
}
static void text(rb_u16 row, rb_u16 col, const char *s, rb_u16 color)
{
    rb_video_text(row * 80 + col, s, color);
}
static void hex(rb_u16 row, rb_u16 col, rb_u32 value, rb_u16 width)
{
    char buffer[9];
    rb_u16 i = width;
    buffer[i] = 0;
    while (i) { buffer[--i] = digits[value & 15]; value >>= 4; }
    text(row, col, buffer, 0x17);
}
static void debug(const char *s)
{
    while (*s) { rb_debug_putc((rb_u8)*s++); }
}
static void debug_hex(rb_u16 value)
{
    rb_u16 i = 4;
    while (i) { --i; rb_debug_putc(digits[(value >> (i * 4)) & 15]); }
}
static void frame(void)
{
    rb_u16 row;
    rb_video_fill(0, 2000, 0x1720);
    rb_video_fill(81, 78, 0x17C4); rb_video_fill(1841, 78, 0x17C4);
    for (row = 2; row < 23; ++row) {
        rb_video_fill(row * 80 + 1, 1, 0x17B3); rb_video_fill(row * 80 + 78, 1, 0x17B3);
    }
    rb_video_fill(81, 1, 0x17DA); rb_video_fill(158, 1, 0x17BF);
    rb_video_fill(1841, 1, 0x17C0); rb_video_fill(1918, 1, 0x17D9);
    text(2, 4, RB_RS_TITLE, 0x1F); text(2, 65, RB_RS_READ_ONLY, 0x1E);
    rb_video_fill(321, 78, 0x17C4);
}
static void draw(rb_u16 boot, rb_u16 view, const rb_rescue_device *d, const rb_rescue_result *r)
{
    frame();
    text(5, 4, RB_RS_SCOPE, 0x1F); text(6, 4, RB_RS_LIMIT, 0x17);
    text(8, 4, !view ? RB_RS_READY : r->status ? reasons[r->status]
        : r->layout ? RB_RS_BAD_LAYOUT : RB_RS_OK, view && !r->status && !r->layout ? 0x1A : 0x1E);
    if (view) {
        text(9, 4, RB_RS_CODES, 0x17);
        hex(9, 32, r->status, 4); text(9, 37, "/", 0x17); hex(9, 39, r->layout, 4);
        text(11, 4, RB_RS_DRIVES, 0x17);
        hex(11, 32, boot, 4); text(11, 37, "/", 0x17); hex(11, 39, 0x80, 4);
        if (d->drive) {
            text(12, 4, RB_RS_ROUTE, 0x17); text(12, 32, d->mode ? "EDD" : "CHS", 0x17);
            text(13, 4, RB_RS_CAPACITY, 0x17);
            hex(13, 32, d->capacity_high, 8); hex(13, 40, d->capacity_low, 8);
            text(14, 4, RB_RS_GEOMETRY_LABEL, 0x17);
            hex(14, 32, d->heads, 4); text(14, 37, "/", 0x17); hex(14, 39, d->sectors_per_track, 4);
        }
        if (!r->status) {
            text(15, 4, RB_RS_DISK_ID, 0x17); hex(15, 32, r->disk_id, 8);
            text(16, 4, RB_RS_CRC, 0x17); hex(16, 32, r->mbr_crc, 8);
            text(17, 4, RB_RS_SIGNATURE, 0x17);
            hex(17, 32, r->signature, 4); text(17, 37, "/", 0x17); hex(17, 39, r->marker, 4);
            text(18, 4, RB_RS_COUNTS, 0x17);
            hex(18, 32, r->entries, 4); text(18, 37, "/", 0x17); hex(18, 39, r->ebrs, 4);
        }
        text(19, 4, RB_RS_LBA, 0x17); hex(19, 32, r->error_lba, 8);
    }
    text(21, 4, RB_RS_HELP, 0x17); text(22, 4, RB_RS_IDENTITY, 0x17);
}

static void draw_file(rb_u16 status, rb_u32 lba, const rb_backup_boot *r)
{
    const char *reason = status == RB_FILE_MISSING ? RB_RS_B_MISSING
        : status == RB_FILE_IO ? RB_RS_B_IO : status ? RB_RS_B_FILE_BAD
        : r->status ? RB_RS_B_BAD : RB_RS_B_OK;
    frame();
    text(5, 4, RB_RS_B_SCOPE, 0x1F); text(6, 4, RB_RS_B_LIMIT, 0x17);
    text(8, 4, reason, !status && !r->status ? 0x1A : 0x1E);
    text(9, 4, RB_RS_B_CODES, 0x17);
    hex(9, 32, status, 4); text(9, 37, "/", 0x17); hex(9, 39, r->status, 4);
    text(9, 44, "/", 0x17); hex(9, 46, r->detail, 4);
    text(10, 4, RB_RS_B_NESTED, 0x17); hex(10, 32, r->record_detail, 4);
    if (!status && !r->status) {
        text(12, 4, RB_RS_B_COUNTS, 0x17);
        hex(12, 32, r->volumes, 4); text(12, 37, "/", 0x17); hex(12, 39, r->fat16, 4);
        text(12, 44, "/", 0x17); hex(12, 46, r->fat32, 4);
        text(13, 4, RB_RS_B_SECTORS, 0x17); hex(13, 32, r->reserved_sectors, 4);
        text(14, 4, RB_RS_B_READY, 0x17); hex(14, 32, r->ready_matches, 4);
    }
    text(16, 4, RB_RS_B_FILE_LBA, 0x17); hex(16, 32, lba, 8);
    text(17, 4, RB_RS_B_DISK_LBA, 0x17); hex(17, 32, r->error_lba, 8);
    text(18, 4, RB_RS_B_EXTENT, 0x17);
    hex(18, 32, r->kind, 4); text(18, 37, "/", 0x17); hex(18, 39, r->index, 4);
    text(21, 4, RB_RS_B_HELP, 0x17); text(22, 4, RB_RS_B_BOUNDARY, 0x17);
}

static void draw_match(const rb_rescue_match *r)
{
    rb_u16 i;
    const rb_backup_target *o = &r->observed;
    const char *reason = RB_RS_T_OK;
    if (r->status == RB_RMATCH_FILE) {
        reason = r->detail == RB_FILE_MISSING ? RB_RS_B_MISSING
            : r->detail == RB_FILE_IO ? RB_RS_B_IO : RB_RS_B_FILE_BAD;
    } else if (r->status == RB_RMATCH_SAVED) { reason = RB_RS_B_BAD; }
    else if (r->status == RB_RMATCH_PROBE) { reason = reasons[r->detail]; }
    else if (r->status == RB_RMATCH_CHANGED) { reason = RB_RS_T_CHANGED; }
    else if (r->status == RB_RMATCH_TARGET) {
        reason = r->detail == RB_BTARGET_CAPACITY ? RB_RS_T_CAPACITY
            : r->detail == RB_BTARGET_GEOMETRY ? RB_RS_T_GEOMETRY
            : r->detail == RB_BTARGET_IDENTITY ? RB_RS_T_IDENTITY
            : r->detail == RB_BTARGET_LAYOUT ? RB_RS_T_LAYOUT
            : r->detail == RB_BTARGET_CHANGED ? RB_RS_T_CHANGED : RB_RS_T_BAD;
    }
    frame(); text(5, 4, RB_RS_T_SCOPE, 0x1F); text(6, 4, RB_RS_T_LIMIT, 0x17);
    text(8, 4, reason, r->status ? 0x1E : 0x1A);
    text(9, 4, RB_RS_T_CODES, 0x17);
    hex(9, 32, r->status, 4); text(9, 37, "/", 0x17); hex(9, 39, r->detail, 4);
    text(9, 44, "/", 0x17); hex(9, 46, r->nested, 4);
    text(10, 4, RB_RS_B_NESTED, 0x17); hex(10, 32, r->record_detail, 4);
    if (!r->status) {
        text(11, 4, RB_RS_DISK_ID, 0x17); hex(11, 32, o->disk_id, 8);
        text(12, 4, RB_RS_T_MEDIA, 0x17);
        for (i = 0; i < 16; ++i) { hex(12, 32 + i * 2, o->media_id[i], 2); }
        text(13, 4, RB_RS_T_CRC, 0x17); hex(13, 32, o->layout_crc, 8);
        text(14, 4, RB_RS_T_ADMIN, 0x17);
        hex(14, 32, o->admin_start, 8); text(14, 41, "/", 0x17); hex(14, 43, o->admin_sectors, 8);
        text(15, 4, RB_RS_CAPACITY, 0x17);
        hex(15, 32, r->device.capacity_high, 8); hex(15, 40, r->device.capacity_low, 8);
        text(16, 4, RB_RS_T_ROUTE, 0x17); text(16, 32, r->device.mode ? "EDD" : "CHS", 0x17);
        text(16, 36, "/", 0x17); hex(16, 38, r->device.heads, 4);
        text(16, 43, "/", 0x17); hex(16, 45, r->device.sectors_per_track, 4);
        text(17, 4, RB_RS_T_GENERATIONS, 0x17);
        hex(17, 32, o->config_generation, 8); text(17, 41, "/", 0x17); hex(17, 43, o->state_generation, 8);
    }
    text(18, 4, RB_RS_B_FILE_LBA, 0x17); hex(18, 32, r->file_lba, 8);
    text(19, 4, RB_RS_T_LBA, 0x17); hex(19, 32, r->disk_lba, 8);
    text(21, 4, RB_RS_T_HELP, 0x17); text(22, 4, RB_RS_T_BOUNDARY, 0x17);
}

void __cdecl rb_rescue_run(rb_u16 boot)
{
    rb_rescue_device device;
    rb_rescue_result result;
    rb_backup_boot backup;
    rb_rescue_match match;
    rb_u16 file_status = 0;
    rb_u32 file_lba = 0;
    rb_u16 key, view = 0, serial = 0;
    clear(&device, sizeof(device)); clear(&result, sizeof(result)); clear(&backup, sizeof(backup));
    clear(&match, sizeof(match));
    rb_video_init(); draw(boot, view, &device, &result);
    debug("RB RESCUE UI " RB_RS_LANGUAGE " CP437\r\nRB RESCUE READY\r\n");
    for (;;) {
        key = rb_key_poll();
        if (key == 0xFFFF) { rb_idle(); continue; }
        if ((key >> 8) == 0x3F || ((key & 0xFF) == 13 && view == 3)) {
            clear(&device, sizeof(device)); clear(&result, sizeof(result)); clear(&backup, sizeof(backup));
            file_status = 0; file_lba = 0;
            debug("RB MATCH BEGIN\r\n");
            rb_rescue_backup_match(boot, &match); view = 3;
            debug("RB MATCH status="); debug_hex(match.status); debug(" detail="); debug_hex(match.detail);
            debug(" nested="); debug_hex(match.nested); debug(" record="); debug_hex(match.record_detail); debug("\r\n");
        } else if ((key >> 8) == 0x3E || ((key & 0xFF) == 13 && view == 2)) {
            clear(&match, sizeof(match));
            clear(&device, sizeof(device)); clear(&result, sizeof(result));
            debug("RB FILE BEGIN\r\n");
            rb_rescue_backup_check(boot, &file_status, &file_lba, &backup);
            view = 2;
            debug("RB FILE status="); debug_hex(file_status);
            debug(" check="); debug_hex(backup.status); debug(" detail="); debug_hex(backup.detail);
            debug(" nested="); debug_hex(backup.record_detail); debug("\r\n");
        } else if ((key & 0xFF) == 13) {
            clear(&match, sizeof(match)); clear(&backup, sizeof(backup)); file_status = 0; file_lba = 0;
            clear(&device, sizeof(device)); clear(&result, sizeof(result));
            debug("RB RESCUE BEGIN\r\n");
            result.status = rb_rescue_probe(&device);
            if (!result.status) { rb_rescue_inspect(&result, &device, rb_disk_read, (void *)0); }
            view = 1;
            debug("RB RESCUE status="); debug_hex(result.status);
            debug(" layout="); debug_hex(result.layout); debug("\r\n");
        } else if ((key & 0xFF) == 27) {
            clear(&match, sizeof(match));
            clear(&device, sizeof(device)); clear(&result, sizeof(result)); clear(&backup, sizeof(backup));
            file_status = 0; file_lba = 0; view = 0;
        }
        if (view == 3) { draw_match(&match); }
        else if (view == 2) { draw_file(file_status, file_lba, &backup); }
        else { draw(boot, view, &device, &result); }
        debug("RB RESCUE KEY "); debug_hex(++serial); debug(" view="); debug_hex(view); debug("\r\n");
    }
}
