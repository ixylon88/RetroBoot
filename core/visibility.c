#include "visibility.h"

typedef struct {
    rb_sector_reader read;
    void *opaque;
    rb_u8 *mbr;
} mbr_capture;

static rb_u16 __cdecl capture_mbr(rb_u32 lba, rb_u8 *sector, void *opaque)
{
    mbr_capture *c = (mbr_capture *)opaque;
    rb_u16 i, status = c->read(lba, sector, c->opaque);

    if (!status && lba == 0) {
        for (i = 0; i < 512; ++i) { c->mbr[i] = sector[i]; }
    }

    return status;
}

static rb_u32 read32(const rb_u8 *p)
{
    return (rb_u32)p[0] | ((rb_u32)p[1] << 8)
        | ((rb_u32)p[2] << 16) | ((rb_u32)p[3] << 24);
}

static rb_u16 visible_type(rb_u16 type)
{
    switch (type) {
    case 0x06: case 0x0E: case 0x0B: case 0x0C: case 0x07:
        return type;
    case 0x16: case 0x1E: case 0x1B: case 0x1C: case 0x17:
        return type - 0x10;
    default:
        return 0;
    }
}

static void clear_plan(rb_visibility_result *r)
{
    rb_u16 i;

    r->current_visible = r->current_active = 0;
    r->wanted_visible = r->wanted_active = r->changed = 0;
    for (i = 0; i < 512; ++i) { r->before[i] = r->after[i] = 0; }
}

void rb_visibility_check(rb_visibility_result *r, const rb_config_result *config,
                         const rb_state_result *state, rb_u16 index,
                         rb_sector_reader read, void *opaque,
                         rb_u32 low, rb_u32 high, rb_u32 admin_lba)
{
    rb_partition_scan scan;
    mbr_capture capture;
    const rb_profile *profile;
    rb_u16 i, type, bit, allowed = 0, admin_hidden = 0;
    rb_u8 *entry;

    clear_plan(r);
    r->status = RB_VISIBILITY_PROOF;
    r->error_lba = 0;
    capture.read = read;
    capture.opaque = opaque;
    capture.mbr = r->before;

    rb_state_check_layout(&r->proof, &scan, config, state, index,
                          capture_mbr, &capture, low, high);
    if (r->proof.status) {
        r->error_lba = r->proof.error_lba;
        clear_plan(r);
        return;
    }

    /* RBL1 intentionally normalizes hidden types and excludes boot-code bytes.
     * The final scan must still find the management volume hidden, and the
     * captured MBR must retain its startup binding before a preview is shown. */
    for (i = 4; i < scan.count; ++i) {
        if (scan.entries[i].start == admin_lba && scan.entries[i].logical
                && (scan.entries[i].type == 0x16 || scan.entries[i].type == 0x1E)) {
            admin_hidden = 1;
        }
    }

    if (!admin_hidden || r->before[432] != 'R' || r->before[433] != 'B'
            || r->before[434] != 'M' || r->before[435] != '1'
            || read32(r->before + 436) != admin_lba) {
        r->status = RB_VISIBILITY_ADMIN;
        r->error_lba = admin_hidden ? 0 : admin_lba;
        clear_plan(r);
        return;
    }

    profile = &config->config.entries[index];
    for (i = 0; i < 4; ++i) {
        if (visible_type(scan.entries[i].type)) { allowed |= 1U << i; }
    }

    /* The loader already validates this mask; retain the API boundary check. */
    bit = 1U << (profile->slot - 1);
    if ((profile->visible_mask & ~allowed) || !(profile->visible_mask & bit)
            || (profile->kind != 1 && profile->kind != 2)
            || (profile->kind == 1 && profile->visible_mask != bit)) {
        r->proof.status = RB_PROOF_CONFIG;
        r->proof.detail = RB_CONFIG_PROFILE;
        r->proof.observed_crc = 0;
        r->proof.matched_index = RB_CONFIG_NONE;
        clear_plan(r);
        return;
    }

    r->wanted_visible = profile->visible_mask;
    r->wanted_active = bit;
    for (i = 0; i < 512; ++i) { r->after[i] = r->before[i]; }

    /* Empty slots and the extended container remain byte-identical. Geometry,
     * slot order, CHS bytes, signatures and all boot-code bytes are preserved. */
    for (i = 0; i < 4; ++i) {
        type = visible_type(scan.entries[i].type);
        if (!type) { continue; }

        bit = 1U << i;
        if (scan.entries[i].type == type) { r->current_visible |= bit; }
        if (scan.entries[i].flag) { r->current_active |= bit; }

        entry = r->after + 446 + i * 16;
        entry[0] = r->wanted_active & bit ? 0x80 : 0;
        entry[4] = (rb_u8)(r->wanted_visible & bit ? type : type + 0x10);
        if (entry[0] != r->before[446 + i * 16] || entry[4] != r->before[450 + i * 16]) {
            r->changed |= bit;
        }
    }

    r->status = r->changed ? RB_VISIBILITY_CHANGE : RB_VISIBILITY_MATCH;
}
