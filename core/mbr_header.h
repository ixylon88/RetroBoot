/* Canonical 512-byte headers shared by MBR history writers. */
#ifndef RB_MBR_HEADER_H
#define RB_MBR_HEADER_H

#include "mbr_restart.h"
#include "mbr_compare.h"
#include "config.h"

static void put32(rb_u8 *out, rb_u32 v)
{
    rb_u16 i;
    for (i = 0; i < 4; ++i) {
        out[i] = (rb_u8)v;
        v >>= 8;
    }
}

static void make_header(rb_u8 *out, const char *tag, const rb_mbr_binding *binding,
                        const rb_mbr_commit *c)
{
    rb_u16 i;
    clear(out, 512);
    for (i = 0; i < 8; ++i) { out[i] = (rb_u8)tag[i]; }
    for (i = 0; i < 16; ++i) {
        out[8 + i] = binding->target.id[i];
        out[32 + i] = binding->recovery_id[i];
    }
    put32(out + 24, binding->target.capacity_low);
    put32(out + 28, binding->target.capacity_high);
    put32(out + 48, c->generation);
    put32(out + 52, c->issued);
    put32(out + 56, c->approved);
    put32(out + 60, c->previous);
    put32(out + 64, c->original_crc);
    put32(out + 68, c->approved_crc);
    put32(out + 508, rb_crc32(out, 508));
}

static __inline void make_witness_header(rb_u8 *out, const rb_mbr_witness *w)
{
    make_header(out, w->alternate_payload ? "RBWIT002" : "RBWIT001", &w->binding, &w->commit);
}

#endif
