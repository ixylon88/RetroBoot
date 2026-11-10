#ifndef RB_CONFIG_H
#define RB_CONFIG_H

#include "volume.h"

#define RB_CONFIG_BYTES 512U
#define RB_CONFIG_MAX 8U
#define RB_CONFIG_NONE 0xFFFFU

enum {
    RB_CONFIG_OK, RB_CONFIG_MISSING, RB_CONFIG_IO, RB_CONFIG_FORMAT,
    RB_CONFIG_CRC, RB_CONFIG_IDENTITY, RB_CONFIG_PROFILE, RB_CONFIG_CONFLICT,
    RB_CONFIG_SCAN, RB_CONFIG_ADMIN, RB_CONFIG_DIRECTORY, RB_CONFIG_FAT
};

typedef struct {
    rb_u32 id, start, sectors;
    rb_u32 install_low, install_high;
    rb_u16 slot, type, kind, installed, approved, visible_mask;
    char name[25];
} rb_profile;

typedef struct {
    rb_u32 generation, disk_id, layout_crc, default_id;
    rb_u16 count, countdown, language, version;
    rb_u8 media_id[16];
    rb_profile entries[RB_CONFIG_MAX];
} rb_config;

typedef struct {
    rb_config config;
    rb_u32 error_lba;
    rb_u16 status, detail, source, copies[2];
} rb_config_result;

rb_u32 rb_crc32(const rb_u8 *data, rb_u16 length);
/* Only a successful, bounded complete partition scan is a valid input. */
rb_u32 rb_layout_crc(const rb_partition_scan *scan);
rb_u16 rb_config_decode(rb_config *result, const rb_u8 *data, rb_u16 length,
                        const rb_partition_scan *scan, const rb_partition *admin);
void rb_config_select(rb_config_result *result, const rb_u8 *a, const rb_u8 *b,
                      rb_u16 readable_mask, const rb_partition_scan *scan,
                      const rb_partition *admin);
/* Read-only, one-sector configuration files in the supported admin FAT16.
 * No result from this API authorizes execution, automatic start or writes. */
void rb_config_load(rb_config_result *result, rb_sector_reader read, void *opaque,
                    rb_u32 low, rb_u32 high, rb_u32 disk_id, rb_u32 admin_lba);
rb_u16 __cdecl rb_config_selftest(void);

#endif
