#include "bios_ui.h"
#include "menu.h"
#include "partitions.h"
#include "stage2.h"
#include "ui_text.h"
#include "volume.h"
#include "config.h"
#include "state.h"
#include "visibility.h"
#include "admin_audit.h"
#include "journal_io.h"
#ifdef RB_PREPARED_DOS
#include "dos_countdown.h"
enum { DOS_TIMER_EDIT = 13, DOS_TIMER_RESULT };
static rb_countdown_edit timer;
static const char * const timer_results[] = {
    RB_UI_TIMER_OK, RB_UI_TIMER_DISK, RB_UI_TIMER_RECORDS, RB_UI_TIMER_CHANGED,
    RB_UI_TIMER_FULL, RB_UI_TIMER_WRITE, RB_UI_TIMER_READBACK, RB_UI_TIMER_UNCHANGED
};
static rb_dos_choice dos_choice;
static rb_u16 dos_status;
#endif
#ifdef RB_HANDOFF_TEST
#include "profile_test.h"
#endif

#define NORMAL 0x17U
#define TITLE 0x1FU
#define SELECTED 0x70U

static const char * const labels[3] = {
    RB_UI_SYSTEM_INFO, RB_UI_PARTITIONS, RB_UI_RECOVERY
};
#ifdef RB_HANDOFF_TEST
static const char * const profile_test_messages[] = {
    "", RB_UI_PROFILE_TEST_SELECTION, RB_UI_PROFILE_TEST_PROOF,
    RB_UI_PROFILE_TEST_CHANGE, RB_UI_PROFILE_TEST_TARGET, RB_UI_PROFILE_TEST_CODE
};
#endif
static const char * const audit_messages[] = {
    RB_UI_AUDIT_OK, RB_UI_AUDIT_SCAN, RB_UI_AUDIT_ADMIN, RB_UI_AUDIT_IO,
    RB_UI_AUDIT_ROOT, RB_UI_AUDIT_CHAIN, RB_UI_AUDIT_SHARED, RB_UI_AUDIT_COPIES,
    RB_UI_AUDIT_HEADER, RB_UI_AUDIT_ORPHAN, RB_UI_AUDIT_CHANGED, RB_UI_AUDIT_BOOTSTRAP
};
static const char * const journal_load_messages[] = {
    "", RB_UI_JOURNAL_ALLOCATION, RB_UI_JOURNAL_CONFIG, RB_UI_JOURNAL_STATE,
    RB_UI_JOURNAL_IDENTITY, RB_UI_JOURNAL_IO, RB_UI_JOURNAL_CHANGED
};
static const char * const journal_observations[] = {
    RB_UI_JOURNAL_INVALID, RB_UI_JOURNAL_BASELINE, RB_UI_JOURNAL_PREPARED_OLD,
    RB_UI_JOURNAL_PREPARED_NEW, RB_UI_JOURNAL_COMMITTED_NEW, RB_UI_JOURNAL_DIVERGED
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
static const char * const config_messages[] = {
    RB_UI_CONFIG_OK, RB_UI_CONFIG_MISSING, RB_UI_ERROR_IO, RB_UI_CONFIG_FORMAT,
    RB_UI_CONFIG_CRC, RB_UI_CONFIG_IDENTITY, RB_UI_CONFIG_PROFILE,
    RB_UI_CONFIG_CONFLICT, RB_UI_SCAN_FAILED, RB_UI_CONFIG_ADMIN,
    RB_UI_CONFIG_DIRECTORY, RB_UI_CONFIG_FAT
};
static const char * const proof_messages[] = {
    RB_UI_STATE_MATCH, RB_UI_STATE_CONFIG, RB_UI_STATE_RECORD, RB_UI_STATE_DEGRADED,
    RB_UI_STATE_LEGACY, RB_UI_STATE_IDENTITY, RB_UI_STATE_EMPTY, RB_UI_STATE_PENDING,
    RB_UI_STATE_INSTALLATION, RB_UI_STATE_TARGET, RB_UI_STATE_NOT_READY, RB_UI_STATE_APPROVAL,
    RB_UI_STATE_SCAN, RB_UI_STATE_LAYOUT, RB_UI_STATE_VOLUME, RB_UI_STATE_VBR
};

static const char * const visibility_messages[] = {
    RB_UI_VIS_MATCH, RB_UI_VIS_CHANGE, RB_UI_VIS_BLOCKED, RB_UI_VIS_ADMIN
};

static void text(rb_u16 row, rb_u16 column, const char *value, rb_u16 color)
{
    rb_video_text(row * 80U + column, value, color);
}

static void cell(rb_u16 row, rb_u16 column, rb_u16 character)
{
    rb_video_fill(row * 80U + column, 1, (NORMAL << 8) | character);
}

static void hex_digits(rb_u16 row, rb_u16 column, rb_u32 value, rb_u16 width)
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

/* Numeric values have one prefix; byte sequences keep their stored order. */
static void hex(rb_u16 row, rb_u16 col, rb_u32 value, rb_u16 width)
{
    text(row, col, "0x", NORMAL); hex_digits(row, col + 2, value, width);
}
static void hex64(rb_u16 row, rb_u16 col, rb_u32 high, rb_u32 low)
{
    hex(row, col, high, 8); hex_digits(row, col + 10, low, 8);
}
static void media_bytes(rb_u16 row, rb_u16 col, const rb_u8 *value)
{
    rb_u16 i;
    for (i = 0; i < 16; ++i) {
        if (i) { text(row, col + i * 3 - 1, " ", NORMAL); }
        hex_digits(row, col + i * 3, value[i], 2);
    }
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
                 const rb_volume_probe *volume, rb_u16 volume_index,
                 const rb_config_result *config, rb_u16 config_index,
                 const rb_state_result *installation, const rb_state_proof *proof,
                 const rb_visibility_result *visibility, const rb_admin_audit *audit,
                 const rb_journal_diagnosis *journal
#ifdef RB_HANDOFF_TEST
                 , rb_u16 handoff_status, rb_u16 handoff_detail, rb_u16 profile_status
#endif
                 )
{
    rb_u16 row, index;
    const rb_partition *p;
    const rb_profile *profile;
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
#ifdef RB_PREPARED_DOS
    if (view == DOS_TIMER_EDIT || view == DOS_TIMER_RESULT) {
        text(5, 4, RB_UI_TIMER_TITLE, TITLE);
        if (view == DOS_TIMER_EDIT) {
            text(8, 4, RB_UI_TIMER_SAVED, NORMAL); decimal(8, 30, timer.saved);
            text(10, 4, RB_UI_TIMER_NEW, TITLE); decimal(10, 30, timer.seconds);
            text(13, 4, RB_UI_TIMER_TARGET, NORMAL);
            text(13, 30, timer.target ? "RBCFG.B" : "RBCFG.A", NORMAL); hex(13, 40, timer.lba, 8);
            text(16, 4, RB_UI_TIMER_RANGE, NORMAL);
            text(20, 4, RB_UI_TIMER_KEYS, NORMAL);
            text(22, 4, RB_UI_TIMER_CONFIRM, NORMAL);
        } else {
            text(8, 4, timer_results[timer.status], TITLE);
            if (timer.status == RB_TIMER_OK || timer.status == RB_TIMER_UNCHANGED) {
                text(10, 4, RB_UI_TIMER_SAVED, NORMAL); decimal(10, 30, timer.saved);
            }
            text(22, 4, RB_UI_TIMER_BACK, NORMAL);
        }
        return;
    }
    if (view != 0 || !dos_choice.selected.valid)
#endif
    { text(2, 65, RB_UI_READ_ONLY, 0x1E); }
    if (view == 0) {
        text(5, 4, RB_UI_BOOT_MENU, TITLE);
#ifdef RB_PREPARED_DOS
        if (dos_choice.selected.valid) {
            rb_u16 color = state->selected == 3 ? SELECTED : NORMAL;
            if (state->selected == 3) {
                rb_video_fill(9 * 80U + 4, 71, 0x7020);
                text(9, 5, ">", color);
            }
            text(9, 8, dos_choice.selected.entry.name, color);
            text(19, 4, RB_UI_TIMER_HELP, NORMAL);
        } else
#endif
        { text(6, 4, RB_UI_NO_PROFILES, NORMAL); }
#ifdef RB_PREPARED_DOS
        if (state->remaining_ticks) { text(7, 4, RB_UI_DOS_TIMER, NORMAL); }
        else
#endif
        { text(7, 4, RB_UI_AUTO_OFF, NORMAL); }
        for (index = 0; index < 3; ++index) {
            row = 9 + index * 2;
#ifdef RB_PREPARED_DOS
            if (dos_choice.selected.valid) { row += 2; }
#endif
            if (state->selected == index) {
                rb_video_fill(row * 80U + 4, 71, 0x7020);
                text(row, 5, ">", SELECTED);
            }
            text(row, 8, labels[index], state->selected == index ? SELECTED : NORMAL);
        }
        text(17, 4, RB_UI_DRIVE, NORMAL);
        hex(17, 19, rb_boot.drive, 2);
        text(20, 4, RB_UI_AUDIT_HELP, NORMAL);
        text(18, 4, rb_boot.io_mode == 1 ? RB_UI_ROUTE_EDD : RB_UI_ROUTE_CHS, NORMAL);
#ifdef RB_HANDOFF_TEST
        text(19, 4, RB_UI_HANDOFF_HELP, 0x1E);
#endif
#ifdef RB_PREPARED_DOS
    } else if (view == 12) {
        text(5, 4, RB_UI_DOS_BLOCKED, TITLE);
        text(8, 4, dos_status == RB_DOS_JOURNAL ? RB_UI_DOS_BASELINE
            : dos_status == RB_DOS_GEOMETRY ? RB_UI_DOS_GEOMETRY
            : dos_status == RB_PROFILE_SELECTION ? RB_UI_PROFILE_TEST_SELECTION
            : dos_status == RB_PROFILE_CHANGE ? RB_UI_VIS_CHANGE
            : visibility->status == RB_VISIBILITY_ADMIN ? RB_UI_VIS_ADMIN
            : proof_messages[visibility->proof.status], 0x1E);
#endif
    } else if (view == 1) {
        text(5, 4, labels[0], TITLE);
        text(7, 4, RB_UI_DRIVE_HEX, NORMAL); hex(7, 29, rb_boot.drive, 2);
        text(8, 4, RB_UI_ROUTE, NORMAL);
        text(8, 29, rb_boot.io_mode == 1 ? "EDD" : "CHS", NORMAL);
        text(10, 4, RB_UI_REACHABLE, NORMAL);
        hex64(11, 6, rb_boot.reachable_sectors_high, rb_boot.reachable_sectors_low);
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
    } else if (view == 6) {
        text(5, 4, RB_UI_CONFIG_TITLE, TITLE);
        text(6, 4, RB_UI_CONFIG_SCOPE, NORMAL);
        if (!config->status && (config->copies[0] || config->copies[1])) {
            text(7, 4, RB_UI_CONFIG_DEGRADED, 0x1E);
        }
        text(8, 4, RB_UI_CONFIG_COPIES, NORMAL);
        hex(8, 29, config->copies[0], 4); text(8, 36, "/", NORMAL); hex(8, 38, config->copies[1], 4);
        text(9, 4, config_messages[config->status], config->status ? 0x1E : NORMAL);
        if (config->status) {
            text(11, 4, RB_UI_LBA_HEX, NORMAL); hex(11, 23, config->error_lba, 8);
            text(12, 4, RB_UI_CONFIG_DETAIL, NORMAL); hex(12, 29, config->detail, 4);
        } else {
            text(10, 4, RB_UI_CONFIG_GENERATION, NORMAL); hex(10, 29, config->config.generation, 8);
            text(10, 40, config->source ? "B" : "A", NORMAL);
            text(11, 4, RB_UI_CONFIG_IDENTITY_LABEL, NORMAL);
            hex(11, 29, config->config.disk_id, 8); hex(11, 40, config->config.layout_crc, 8);
            if (!config->config.count) { text(14, 4, RB_UI_CONFIG_EMPTY, NORMAL); }
            else {
                profile = &config->config.entries[config_index];
                text(13, 4, profile->name, TITLE);
                text(14, 4, RB_UI_CONFIG_ENTRY, NORMAL); hex(14, 29, profile->id, 8);
                text(14, 40, "P", NORMAL); decimal(14, 41, profile->slot); hex(14, 46, profile->type, 2);
                text(15, 4, RB_UI_CONFIG_EXTENT, NORMAL); hex(15, 29, profile->start, 8); hex(15, 40, profile->sectors, 8);
                text(16, 4, profile->kind == 1 ? "dos9x_isolated" : "nt_chain", NORMAL);
                text(16, 29, RB_UI_CONFIG_FLAGS, NORMAL);
                decimal(16, 57, profile->installed); decimal(16, 61, profile->approved); hex(16, 65, profile->visible_mask, 2);
                text(18, 4, RB_UI_PAGE, NORMAL); decimal(18, 10, config_index + 1);
                text(18, 12, "/", NORMAL); decimal(18, 14, config->config.count);
            }
        }
        text(19, 4, RB_UI_CONFIG_HELP, NORMAL);
    } else if (view == 7) {
        text(5, 4, RB_UI_STATE_TITLE, TITLE); text(6, 4, RB_UI_STATE_SCOPE, NORMAL);
        text(7, 4, RB_UI_STATE_CONFIG_COPIES, NORMAL);
        hex(7, 29, config->copies[0], 4); text(7, 36, "/", NORMAL); hex(7, 38, config->copies[1], 4);
        text(8, 4, RB_UI_STATE_COPIES, NORMAL);
        hex(8, 29, installation->copies[0], 4); text(8, 36, "/", NORMAL); hex(8, 38, installation->copies[1], 4);
        if (!installation->status) {
            text(9, 4, RB_UI_CONFIG_GENERATION, NORMAL); hex(9, 29, installation->state.generation, 8);
            text(9, 40, installation->source ? "B" : "A", NORMAL);
            text(10, 4, RB_UI_STATE_MEDIA, NORMAL);
            media_bytes(10, 29, installation->state.media_id);
        }
        text(12, 4, proof_messages[proof->status], proof->status ? 0x1E : 0x1A);
        text(13, 4, RB_UI_STATE_REASON, NORMAL);
        hex(13, 29, proof->status, 4); text(13, 36, "/", NORMAL); hex(13, 38, proof->detail, 4);
        if (!config->status && config_index < config->config.count) {
            profile = &config->config.entries[config_index];
            text(14, 4, profile->name, TITLE);
            text(15, 4, RB_UI_STATE_INSTALL_ID, NORMAL);
            hex64(15, 29, profile->install_high, profile->install_low);
            text(18, 4, RB_UI_PAGE, NORMAL); decimal(18, 10, config_index + 1);
            text(18, 12, "/", NORMAL); decimal(18, 14, config->config.count);
        }
        if (!proof->status) {
            text(17, 4, RB_UI_STATE_CRC, NORMAL); hex(17, 29, proof->observed_crc, 8);
        } else {
            text(17, 4, RB_UI_LBA_HEX, NORMAL); hex(17, 23, proof->error_lba, 8);
        }
        text(19, 4, RB_UI_STATE_HELP, NORMAL);
    } else if (view == 8) {
        text(5, 4, RB_UI_VIS_TITLE, TITLE);
        text(6, 4, RB_UI_VIS_SCOPE, NORMAL);
        text(8, 4, visibility_messages[visibility->status], visibility->status ? 0x1E : 0x1A);

        text(9, 4, RB_UI_VIS_CODES, NORMAL);
        hex(9, 30, visibility->status, 4); text(9, 37, "/", NORMAL);
        hex(9, 39, visibility->proof.status, 4); text(9, 46, "/", NORMAL);
        hex(9, 48, visibility->proof.detail, 4);

        if (!config->status && config_index < config->config.count) {
            text(7, 4, config->config.entries[config_index].name, TITLE);
            text(18, 4, RB_UI_PAGE, NORMAL);
            decimal(18, 10, config_index + 1); text(18, 12, "/", NORMAL);
            decimal(18, 14, config->config.count);
        }

        if (visibility->status <= RB_VISIBILITY_CHANGE) {
            text(10, 4, RB_UI_VIS_COLUMNS, NORMAL);
            for (index = 0; index < 4; ++index) {
                text(11 + index, 4, "P", NORMAL); decimal(11 + index, 5, index + 1);
                hex(11 + index, 17, visibility->before[450 + index * 16], 2);
                text(11 + index, 22, "/", NORMAL);
                hex(11 + index, 25, visibility->before[446 + index * 16], 2);
                hex(11 + index, 45, visibility->after[450 + index * 16], 2);
                text(11 + index, 50, "/", NORMAL);
                hex(11 + index, 53, visibility->after[446 + index * 16], 2);
            }

            text(15, 4, RB_UI_VIS_VISIBLE, NORMAL);
            hex(15, 30, visibility->current_visible, 2); text(15, 35, "/", NORMAL);
            hex(15, 38, visibility->wanted_visible, 2);
            text(16, 4, RB_UI_VIS_ACTIVE, NORMAL);
            hex(16, 30, visibility->current_active, 2); text(16, 35, "/", NORMAL);
            hex(16, 38, visibility->wanted_active, 2);
            text(17, 4, RB_UI_VIS_CHANGED, NORMAL); hex(17, 30, visibility->changed, 2);
        } else {
            if (visibility->status == RB_VISIBILITY_PROOF) {
                text(11, 4, proof_messages[visibility->proof.status], 0x1E);
            }
            text(13, 4, RB_UI_LBA_HEX, NORMAL); hex(13, 23, visibility->error_lba, 8);
        }

        text(19, 4, RB_UI_VIS_HELP, NORMAL);
#ifdef RB_HANDOFF_TEST
        text(20, 4, RB_UI_PROFILE_TEST_HELP, 0x1E);
    } else if (view == 5) {
        text(5, 4, RB_UI_HANDOFF_FAILED, TITLE);
        text(6, 4, handoff_status == RB_HANDOFF_SCAN ? scan_errors[handoff_detail]
             : handoff_status == RB_HANDOFF_VOLUME ? volume_messages[handoff_detail]
             : handoff_status == RB_HANDOFF_TARGET ? RB_UI_HANDOFF_TARGET : RB_UI_HANDOFF_CODE, 0x1E);
        text(8, 4, RB_UI_HANDOFF_REASON, NORMAL);
        hex(10, 4, handoff_status, 4); text(10, 11, "/", NORMAL);
        hex(10, 13, handoff_detail, 4);
        text(13, 4, RB_UI_NO_CHANGES, NORMAL);
        text(18, 4, RB_UI_HANDOFF_RETRY, NORMAL);
    } else if (view == 9) {
        text(5, 4, RB_UI_PROFILE_TEST_FAILED, TITLE);
        text(6, 4, profile_test_messages[profile_status], 0x1E);
        text(8, 4, RB_UI_PROFILE_TEST_REASON, NORMAL);
        hex(10, 4, profile_status, 4); text(10, 11, "/", NORMAL);
        hex(10, 13, profile_status == RB_PROFILE_TEST_PROOF ? visibility->proof.status : 0, 4);
        text(10, 20, "/", NORMAL);
        hex(10, 22, profile_status == RB_PROFILE_TEST_PROOF ? visibility->proof.detail : 0, 4);
        if (profile_status == RB_PROFILE_TEST_PROOF) {
            text(12, 4, visibility->status == RB_VISIBILITY_ADMIN ? RB_UI_VIS_ADMIN
                : proof_messages[visibility->proof.status], 0x1E);
        }
        text(14, 4, RB_UI_LBA_HEX, NORMAL); hex(14, 23, visibility->error_lba, 8);
        text(17, 4, RB_UI_NO_CHANGES, NORMAL);
        text(19, 4, RB_UI_PROFILE_TEST_REVIEW, NORMAL);
#endif
    } else if (view == 10) {
        text(5, 4, RB_UI_AUDIT_TITLE, TITLE);
        text(6, 4, RB_UI_AUDIT_SCOPE, NORMAL);
        text(7, 4, RB_UI_AUDIT_LIMIT, NORMAL);
        text(8, 4, audit_messages[audit->status], audit->status ? 0x1E : 0x1A);
        text(9, 4, RB_UI_AUDIT_CODES, NORMAL);
        hex(9, 32, audit->status, 4); text(9, 39, "/", NORMAL); hex(9, 41, audit->detail, 4);
        if (!audit->status) {
            text(10, 4, RB_UI_AUDIT_COLUMNS, NORMAL);
            for (index = 0; index < RB_AUDIT_FILES; ++index) {
                text(11 + index, 4, rb_audit_names[index], TITLE);
                hex(11 + index, 17, audit->files[index].bytes, 8);
                hex(11 + index, 30, audit->files[index].clusters, 4);
                hex(11 + index, 41, audit->files[index].first_lba, 8);
            }
            text(19, 4, RB_UI_AUDIT_CLUSTERS, NORMAL);
            hex(19, 38, audit->total_clusters, 4); text(19, 45, "/", NORMAL);
            hex(19, 47, audit->used_clusters, 4); text(19, 54, "/", NORMAL);
            hex(19, 56, audit->free_clusters, 4);
        } else {
            text(11, 4, RB_UI_LBA_HEX, NORMAL); hex(11, 32, audit->error_lba, 8);
            text(13, 4, RB_UI_AUDIT_ERROR_FILE, NORMAL);
            hex(13, 32, audit->error_file, 4); text(13, 39, "/", NORMAL); hex(13, 41, audit->error_cluster, 4);
        }
        text(20, 4, RB_UI_AUDIT_REVIEW, NORMAL);
    } else if (view == 11) {
        text(5, 4, RB_UI_JOURNAL_TITLE, TITLE);
        text(6, 4, RB_UI_JOURNAL_SCOPE, NORMAL);
        text(8, 4, journal->status ? journal_load_messages[journal->status]
            : journal->journal.status ? RB_UI_JOURNAL_INVALID
            : journal_observations[journal->journal.observation],
            !journal->status && !journal->journal.status
                && (journal->journal.observation == RB_TX_BASELINE
                    || journal->journal.observation == RB_TX_COMMITTED_NEW) ? 0x1A : 0x1E);
        text(9, 4, RB_UI_JOURNAL_LOAD_CODES, NORMAL);
        hex(9, 32, journal->status, 4); text(9, 39, "/", NORMAL); hex(9, 41, journal->detail, 4);
        text(10, 4, RB_UI_JOURNAL_COPY_CODES, NORMAL);
        hex(10, 32, journal->journal.status, 4); text(10, 39, "/", NORMAL);
        hex(10, 41, journal->journal.copies[0], 4); text(10, 48, "/", NORMAL);
        hex(10, 50, journal->journal.copies[1], 4);
        if (!journal->status && !journal->journal.status) {
            text(12, 4, RB_UI_JOURNAL_SEQUENCE, NORMAL); hex(12, 32, journal->journal.record.sequence, 8);
            text(13, 4, RB_UI_JOURNAL_PHASE, NORMAL);
            hex(13, 32, journal->journal.record.phase, 4); text(13, 39, "/", NORMAL);
            text(13, 41, journal->journal.source ? "B" : "A", NORMAL);
            text(14, 4, RB_UI_JOURNAL_CRCS, NORMAL);
            hex(14, 32, journal->journal.record.before_crc, 8); text(14, 43, "/", NORMAL);
            hex(14, 45, journal->journal.record.after_crc, 8);
            text(15, 4, RB_UI_VIS_CHANGED, NORMAL); hex(15, 32, journal->journal.record.changed, 2);
        }
        text(17, 4, RB_UI_LBA_HEX, NORMAL); hex(17, 32, journal->error_lba, 8);
        text(19, 4, RB_UI_JOURNAL_HELP, NORMAL);
        text(20, 4, RB_UI_NO_CHANGES, NORMAL);
    } else {
        text(5, 4, labels[2], TITLE);
        text(8, 4, RB_UI_RECOVERY_MISSING, NORMAL);
        text(10, 4, RB_UI_RECOVERY_PAGES, NORMAL);
        text(13, 4, RB_UI_RECOVERY_READ_ONLY, NORMAL);
        text(18, 4, RB_UI_AUDIT_HELP, NORMAL);
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
    rb_config_result config;
    rb_state_result installation;
    rb_state_proof proof;
    rb_visibility_result visibility;
    rb_menu_state state;
    rb_u16 key, action, rescan, verify_state, view = 0, serial = 0, page = 0;
    rb_u16 probe, volume_index = RB_MENU_NONE;
    rb_u16 config_index = 0;
    rb_admin_audit audit;
    rb_journal_diagnosis journal;
#ifdef RB_HANDOFF_TEST
    rb_u16 handoff_status = 0, handoff_detail = 0, profile_status = 0;
#endif
    rb_u32 now;
    rb_loader_copy(&snapshot);
#ifdef RB_PREPARED_DOS
    rb_dos_open(&dos_choice, &config, &snapshot);
    if (dos_choice.selected.valid) {
        rb_menu_init(&state, 4, 15, 3, (dos_choice.countdown * 182U + 9U) / 10U, rb_ticks());
    } else
#endif
    { rb_menu_init(&state, 3, 7, 0, 0, rb_ticks()); }
    rb_video_init();
    draw(&state, view, &snapshot, &scan, page, &volume, volume_index, &config, config_index, &installation, &proof, &visibility, &audit, &journal
#ifdef RB_HANDOFF_TEST
         , handoff_status, handoff_detail, profile_status
#endif
         );
    debug_state(serial, view, state.selected, page);
    debug_text("RB UI " RB_UI_LANGUAGE " CP437\r\n");
    debug_text("RB MENU READY\r\n");
    for (;;) {
        key = rb_key_poll();
        now = rb_ticks();
        action = view == 0 ? rb_menu_step(&state, key, now) : RB_MENU_NONE;
        if (key == RB_KEY_NONE && action == RB_MENU_NONE) {
            rb_idle();
            continue;
        }
        rescan = 0; probe = 0; verify_state = 0;
        state.remaining_ticks = 0;
#ifdef RB_PREPARED_DOS
        if (action == 3) {
            dos_status = rb_dos_start(&dos_choice, key == RB_KEY_NONE, &config, &installation,
                                      &visibility, &journal, &snapshot);
            debug_text("RB DOS REJECT "); debug_hex(dos_status); debug_text("\r\n");
            view = 12;
        } else
#endif
        if (action != RB_MENU_NONE) { view = action + 1; rescan = view == 2; }
        if ((key & 0xFFU) == 27U) {
            view = 0;
#ifdef RB_PREPARED_DOS
        } else if (view == DOS_TIMER_EDIT) {
            switch (key >> 8) {
            case 0x4B: if (timer.seconds) { --timer.seconds; } break;
            case 0x4D: if (timer.seconds < 60) { ++timer.seconds; } break;
            case 0x47: timer.seconds = 0; break;
            case 0x4F: timer.seconds = 60; break;
            }
            if ((key & 0xFFU) == 13U) {
                rb_countdown_save(&timer, &dos_choice, &snapshot);
                if (!timer.status) { dos_choice.countdown = timer.saved; }
                debug_text("RB TIMER SAVE "); debug_hex(timer.status); debug_text("\r\n");
                view = DOS_TIMER_RESULT;
            }
        } else if (view == DOS_TIMER_RESULT) {
            continue; /* Esc returns to the menu. Enter never retries the write. */
        } else if ((key >> 8) == 0x43U && view == 0 && dos_choice.selected.valid) {
            rb_countdown_open(&timer, &dos_choice, &snapshot);
            view = timer.status ? DOS_TIMER_RESULT : DOS_TIMER_EDIT;
            debug_text("RB TIMER OPEN "); debug_hex(timer.status); debug_text("\r\n");
#endif
        } else if ((key >> 8) == 0x3CU) {
            state.selected = 1; view = 2; rescan = 1;
        } else if ((key >> 8) == 0x3DU) {
            if (view != 4) { volume_index = RB_MENU_NONE; }
            state.selected = 1; view = 2; rescan = 2;
#ifdef RB_HANDOFF_TEST
        } else if ((key >> 8) == 0x3EU && (view == 0 || view == 5)) {
            debug_text("RB HANDOFF BEGIN\r\n");
            handoff_status = rb_run_handoff_test(&handoff_detail);
            debug_text("RB HANDOFF REJECT status="); debug_hex(handoff_status);
            debug_text(" detail="); debug_hex(handoff_detail); debug_text("\r\n");
            view = 5;
        } else if ((key >> 8) == 0x43U && view == 8) {
            debug_text("RB PROFILE BEGIN\r\n");
            profile_status = rb_run_profile_test(&config, &installation, &visibility, &config_index,
                read32(snapshot.mbr + 440), read32(snapshot.mbr + 436));
            debug_text("RB PROFILE REJECT status="); debug_hex(profile_status);
            debug_text(" proof="); debug_hex(visibility.proof.status);
            debug_text(" detail="); debug_hex(visibility.proof.detail);
            debug_text(" index="); debug_hex(config_index); debug_text("\r\n");
            view = 9;
#endif
        } else if ((key >> 8) == 0x3FU) {
            view = 6; config_index = 0;
            debug_text("RB CONFIG BEGIN\r\n");
            rb_config_load(&config, rb_disk_read, (void *)0,
                rb_boot.reachable_sectors_low, rb_boot.reachable_sectors_high,
                read32(snapshot.mbr + 440), read32(snapshot.mbr + 436));
            debug_text("RB CONFIG status="); debug_hex(config.status);
            debug_text(" copies="); debug_hex(config.copies[0]); debug_hex(config.copies[1]);
            debug_text(" source="); debug_hex(config.source);
            debug_text(" count="); debug_hex(config.config.count); debug_text("\r\n");
        } else if ((key >> 8) == 0x40U || (key >> 8) == 0x41U) {
            view = (key >> 8) == 0x40U ? 7 : 8;
            config_index = 0; verify_state = view - 6;
            debug_text(view == 7 ? "RB STATE BEGIN\r\n" : "RB VISIBILITY BEGIN\r\n");
            rb_config_load(&config, rb_disk_read, (void *)0,
                rb_boot.reachable_sectors_low, rb_boot.reachable_sectors_high,
                read32(snapshot.mbr + 440), read32(snapshot.mbr + 436));
            rb_state_load(&installation, rb_disk_read, (void *)0,
                rb_boot.reachable_sectors_low, rb_boot.reachable_sectors_high,
                read32(snapshot.mbr + 440), read32(snapshot.mbr + 436));
            debug_text(view == 7 ? "RB STATE records=" : "RB VISIBILITY records="); debug_hex(installation.status);
            debug_text(" copies="); debug_hex(installation.copies[0]); debug_hex(installation.copies[1]);
            debug_text(" source="); debug_hex(installation.source); debug_text("\r\n");
        } else if ((key >> 8) == 0x44U) {
            view = 10;
            debug_text("RB AUDIT BEGIN\r\n");
            rb_audit_admin(&audit, rb_disk_read, (void *)0,
                rb_boot.reachable_sectors_low, rb_boot.reachable_sectors_high,
                read32(snapshot.mbr + 440), read32(snapshot.mbr + 436));
            debug_text("RB AUDIT status="); debug_hex(audit.status);
            debug_text(" detail="); debug_hex(audit.detail);
            debug_text(" file="); debug_hex(audit.error_file);
            debug_text(" cluster="); debug_hex(audit.error_cluster); debug_text("\r\n");
        } else if ((key >> 8) == 0x42U) {
            state.selected = 2; view = 3;
        } else if ((view == 3 || view == 11) && (key & 0xFFU) == 13U && action == RB_MENU_NONE) {
            view = 11;
            debug_text("RB JOURNAL BEGIN\r\n");
            rb_journal_load(&journal, rb_disk_read, (void *)0,
                rb_boot.reachable_sectors_low, rb_boot.reachable_sectors_high,
                read32(snapshot.mbr + 440), read32(snapshot.mbr + 436),
                rb_boot.io_mode == 1 ? 1 : 2,
                rb_boot.io_mode == 1 ? 0 : (rb_u16)snapshot.heads,
                rb_boot.io_mode == 1 ? 0 : (rb_u16)snapshot.sectors_per_track);
            debug_text("RB JOURNAL load="); debug_hex(journal.status);
            debug_text(" detail="); debug_hex(journal.detail);
            debug_text(" status="); debug_hex(journal.journal.status);
            debug_text(" copies="); debug_hex(journal.journal.copies[0]); debug_hex(journal.journal.copies[1]);
            debug_text(" observation="); debug_hex(journal.journal.observation); debug_text("\r\n");
        } else if ((view == 6 || view == 7 || view == 8) && config.status == 0 && config.config.count
                && ((key >> 8) == 0x4BU || (key >> 8) == 0x4DU)) {
            config_index = (key >> 8) == 0x4BU
                ? (config_index == 0 ? config.config.count - 1 : config_index - 1)
                : (config_index + 1 == config.config.count ? 0 : config_index + 1);
            verify_state = view >= 7 ? view - 6 : 0;
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
        if (verify_state == 1) {
            rb_state_check(&proof, &config, &installation, config_index, rb_disk_read, (void *)0,
                           rb_boot.reachable_sectors_low, rb_boot.reachable_sectors_high);
            debug_text("RB STATE proof="); debug_hex(proof.status);
            debug_text(" detail="); debug_hex(proof.detail); debug_text(" index="); debug_hex(config_index);
            debug_text(" crc="); debug_hex((rb_u16)(proof.observed_crc >> 16)); debug_hex((rb_u16)proof.observed_crc);
            debug_text("\r\n");
        }
        if (verify_state == 2) {
            rb_visibility_check(&visibility, &config, &installation, config_index,
                rb_disk_read, (void *)0, rb_boot.reachable_sectors_low,
                rb_boot.reachable_sectors_high, read32(snapshot.mbr + 436));

            debug_text("RB VISIBILITY status="); debug_hex(visibility.status);
            debug_text(" proof="); debug_hex(visibility.proof.status);
            debug_text(" detail="); debug_hex(visibility.proof.detail);
            debug_text(" index="); debug_hex(config_index);
            debug_text(" changed="); debug_hex(visibility.changed); debug_text("\r\n");
        }
        draw(&state, view, &snapshot, &scan, page, &volume, volume_index, &config, config_index, &installation, &proof, &visibility, &audit, &journal
#ifdef RB_HANDOFF_TEST
             , handoff_status, handoff_detail, profile_status
#endif
             );
        debug_state(++serial, view, state.selected, page);
    }
}
