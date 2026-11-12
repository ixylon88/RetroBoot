#ifndef RB_STATE_H
#define RB_STATE_H

#include "config.h"

enum {
    RB_INSTALL_PLANNED = 1, RB_INSTALL_PREPARED, RB_INSTALL_MEDIA_HANDOFF,
    RB_INSTALL_SETUP, RB_INSTALL_VERIFY, RB_INSTALL_READY, RB_INSTALL_RECOVERY
};

typedef struct {
    rb_u32 install_low, install_high, start, sectors, vbr_crc;
    rb_u16 slot, type, kind, phase;
} rb_installation;

typedef struct {
    rb_u32 generation, disk_id, layout_crc;
    rb_u8 media_id[16];
    rb_u16 count;
    rb_installation entries[4];
} rb_install_state;

typedef struct {
    rb_install_state state;
    rb_u32 error_lba;
    rb_u16 status, detail, source, copies[2];
} rb_state_result;

enum {
    RB_PROOF_MATCH, RB_PROOF_CONFIG, RB_PROOF_STATE, RB_PROOF_DEGRADED,
    RB_PROOF_LEGACY, RB_PROOF_IDENTITY, RB_PROOF_EMPTY, RB_PROOF_PENDING,
    RB_PROOF_INSTALLATION, RB_PROOF_TARGET, RB_PROOF_NOT_READY, RB_PROOF_APPROVAL,
    RB_PROOF_SCAN, RB_PROOF_LAYOUT, RB_PROOF_VOLUME, RB_PROOF_VBR
};

typedef struct {
    rb_u32 error_lba, observed_crc;
    rb_u16 status, detail, matched_index;
} rb_state_proof;

/* Record status codes use the RB_CONFIG_* vocabulary; no boot authority. */
rb_u16 rb_state_decode(rb_install_state *result, const rb_u8 *data, rb_u16 length,
                       const rb_partition_scan *scan, const rb_partition *admin);
void rb_state_select(rb_state_result *result, const rb_u8 *a, const rb_u8 *b,
                     rb_u16 readable_mask, const rb_partition_scan *scan, const rb_partition *admin);
void rb_state_load(rb_state_result *result, rb_sector_reader read, void *opaque,
                   rb_u32 low, rb_u32 high, rb_u32 disk_id, rb_u32 admin_lba);
void rb_state_check(rb_state_proof *result, const rb_config_result *config,
                    const rb_state_result *state, rb_u16 index, rb_sector_reader read,
                    void *opaque, rb_u32 low, rb_u32 high);
/* The complete scan is returned only with a matching record/VBR result. */
void rb_state_check_layout(rb_state_proof *result, rb_partition_scan *scan,
                           const rb_config_result *config, const rb_state_result *state,
                           rb_u16 index, rb_sector_reader read, void *opaque,
                           rb_u32 low, rb_u32 high);
rb_u16 __cdecl rb_state_selftest(void);

#endif
