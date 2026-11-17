#include "backup_stream.h"
#include "backup_encode.h"
#include "backup_format.h"
#include "fingerprint.h"

static rb_u16 fail(rb_backup_stream_result *r, rb_u16 status, rb_u16 detail,
    rb_u16 kind, rb_u16 index, rb_u32 pos)
{
    r->status = status; r->detail = detail; r->kind = kind; r->index = index;
    r->file_sector = pos; r->sectors = 0;
    return status;
}

rb_u16 rb_backup_stream(rb_backup_stream_result *r, const rb_backup *b,
    rb_u32 size, rb_backup_source source, void *source_opaque,
    rb_backup_sink sink, void *sink_opaque)
{
    rb_u8 sector[512];
    rb_u16 pass, i, status;
    rb_u32 pos, offset, crc, digest[2], first[2];
    const rb_backup_extent *e;

    if (!r) { return RB_STREAM_PARAMS; }
    fail(r, RB_STREAM_PARAMS, 0, 0, 0, 0);
    if (!b || !source || !sink) { return r->status; }

    for (pass = 0; pass < 2; ++pass) {
        digest[0] = digest[1] = 0;
        for (i = 0; i < 5; ++i) {
            status = rb_backup_encode_metadata(b, size, i, sector);
            if (status) { return fail(r, RB_STREAM_METADATA, status, 0, 0, i); }
            rb_fingerprint_sector(digest, i, sector);
            if (pass && sink(i, sector, sink_opaque)) {
                return fail(r, RB_STREAM_SINK, 0, 0, 0, i);
            }
        }
        for (i = 0; i < b->count; ++i) {
            e = &b->entries[i]; crc = 0xFFFFFFFFUL;
            for (offset = 0; offset < e->sectors; ++offset) {
                pos = e->file_sector + offset;
                if (source(e->kind, e->index, offset, sector, source_opaque)) {
                    return fail(r, RB_STREAM_READ, 0, e->kind, e->index, pos);
                }
                crc = rb_backup_crc_update(crc, sector, 512);
                rb_fingerprint_sector(digest, pos, sector);
                if (pass && sink(pos, sector, sink_opaque)) {
                    return fail(r, RB_STREAM_SINK, 0, e->kind, e->index, pos);
                }
            }
            if ((crc ^ 0xFFFFFFFFUL) != e->crc) {
                return fail(r, RB_STREAM_CRC, 0, e->kind, e->index, e->file_sector);
            }
        }
        if (!pass) { first[0] = digest[0]; first[1] = digest[1]; }
        else if (digest[0] != first[0] || digest[1] != first[1]) {
            return fail(r, RB_STREAM_CHANGED, 0, 0, 0, 0);
        }
    }
    fail(r, RB_STREAM_OK, 0, 0, 0, 0); r->sectors = size;
    return RB_STREAM_OK;
}
