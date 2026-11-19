#include "mbr_restart.h"
#include "config.h"
#include "mbr_bytes.h"
#include "mbr_media.h"

static rb_u32 le32(const rb_u8 *p)
{
    return (rb_u32)p[0] | ((rb_u32)p[1] << 8) | ((rb_u32)p[2] << 16) | ((rb_u32)p[3] << 24);
}

static int zero(const rb_u8 *p, rb_u16 n)
{
    while (n) { if (p[--n]) { return 0; } }
    return 1;
}

static int valid_commit(const rb_mbr_commit *c)
{
    return c->issued && c->generation >= c->issued && c->approved <= c->issued && c->approved != 1
        && (!c->previous || (c->previous >= 2 && c->previous < c->approved))
        && (c->approved || !c->approved_crc)
        && (c->generation != 1 || (c->issued == 1 && !c->approved));
}

static rb_u16 header(const rb_u8 *p, const char *magic, const rb_mbr_binding *b,
                     rb_mbr_commit *c)
{
    rb_mbr_binding actual;
    rb_u16 i;
    if (!equal(p, (const rb_u8 *)magic, 8) || !zero(p + 72, 436)) { return RB_REOPEN_FORMAT; }
    if (le32(p + 508) != rb_crc32(p, 508)) { return RB_REOPEN_CRC; }
    for (i = 0; i < 16; ++i) {
        actual.target.id[i] = p[8 + i];
        actual.recovery_id[i] = p[32 + i];
    }
    actual.target.capacity_low = le32(p + 24);
    actual.target.capacity_high = le32(p + 28);
    if (!same_binding(&actual, b)) { return RB_REOPEN_BINDING; }
    c->generation = le32(p + 48); c->issued = le32(p + 52);
    c->approved = le32(p + 56); c->previous = le32(p + 60);
    c->original_crc = le32(p + 64); c->approved_crc = le32(p + 68);
    return valid_commit(c) ? RB_REOPEN_OK : RB_REOPEN_FORMAT;
}

static int same_commit(const rb_mbr_commit *a, const rb_mbr_commit *b)
{
    return a->generation == b->generation && a->issued == b->issued
        && a->approved == b->approved && a->previous == b->previous
        && a->original_crc == b->original_crc && a->approved_crc == b->approved_crc;
}

static rb_u16 load(rb_mbr_witness *w, const rb_mbr_binding *b, const rb_u8 *id,
                   const rb_mbr_restart_source *s)
{
    rb_u8 buf[512];
    rb_u16 rc, pass;
    rb_mbr_commit c;
    for (pass = 0; pass < 2; ++pass) {
        rc = acquire(s, id, 0, buf);
        if (!rc) { rc = header(buf, "RBWIT001", b, &c); }
        if (rc) { return rc; }
        if (pass && !same_commit(&w->commit, &c)) { return RB_REOPEN_CHANGED; }
        w->commit = c;
        rc = acquire(s, id, 1, buf);
        if (rc) { return rc; }
        if (rb_crc32(buf, 512) != c.original_crc) { return RB_REOPEN_CRC; }
        if (equal(buf + 432, (const rb_u8 *)"RBM1", 4)) { return RB_REOPEN_FORMAT; }
        if (pass && !equal(w->original, buf, 512)) { return RB_REOPEN_CHANGED; }
        copy_sector(w->original, buf);
        rc = acquire(s, id, 2, buf);
        if (rc) { return rc; }
        if (!c.approved && !zero(buf, 512)) { return RB_REOPEN_FORMAT; }
        if (c.approved && rb_crc32(buf, 512) != c.approved_crc) { return RB_REOPEN_CRC; }
        if (pass && !equal(w->approved, buf, 512)) { return RB_REOPEN_CHANGED; }
        copy_sector(w->approved, buf);
    }
    w->binding = *b;
    return RB_REOPEN_OK;
}

rb_u16 rb_mbr_load_witness(rb_mbr_witness *w, const rb_mbr_binding *b,
                           const rb_u8 *id, const rb_mbr_restart_source *s)
{
    rb_u16 rc;
    if (!w) { return RB_REOPEN_PARAMS; }
    clear((rb_u8 *)w, sizeof(*w));
    if (!b || !id || !s || !s->read) { return RB_REOPEN_PARAMS; }
    if (!valid_witness_binding(b, id)) { return RB_REOPEN_BINDING; }
    rc = load(w, b, id, s);
    if (rc) { clear((rb_u8 *)w, sizeof(*w)); }
    return rc;
}

rb_u16 rb_mbr_verify_witness(const rb_mbr_witness *expected, const rb_u8 *id,
                             const rb_mbr_restart_source *source)
{
    rb_mbr_witness actual;
    rb_u16 rc;
    if (!expected) { return RB_REOPEN_PARAMS; }
    rc = rb_mbr_load_witness(&actual, &expected->binding, id, source);
    if (rc) { return rc; }
    if (!same_commit(&actual.commit, &expected->commit)
        || !equal(actual.original, expected->original, 512)
        || !equal(actual.approved, expected->approved, 512)) { return RB_REOPEN_CHANGED; }
    return RB_REOPEN_OK;
}

static rb_u16 check_carrier(const rb_mbr_witness *w, const rb_mbr_restart_source *s)
{
    rb_mbr_commit c;
    rb_u8 buf[512];
    const rb_u8 *id = w->binding.recovery_id;
    rb_u16 slot = (w->commit.generation & 1) ? 2 : 4;
    rb_u16 rc = acquire(s, id, 0, buf);
    if (!rc) { rc = header(buf, "RBORG001", &w->binding, &c); }
    if (rc) { return rc; }
    if (c.generation != 1 || c.original_crc != w->commit.original_crc) { return RB_REOPEN_CHANGED; }
    rc = acquire(s, id, 1, buf);
    if (rc) { return rc; }
    if (!equal(buf, w->original, 512)) { return RB_REOPEN_CHANGED; }
    rc = acquire(s, id, slot, buf);
    if (!rc) { rc = header(buf, "RBCMT001", &w->binding, &c); }
    if (rc) { return rc; }
    if (!same_commit(&c, &w->commit)) { return RB_REOPEN_STALE; }
    rc = acquire(s, id, slot + 1, buf);
    if (rc) { return rc; }
    return equal(buf, w->approved, 512) ? RB_REOPEN_OK : RB_REOPEN_CHANGED;
}

rb_u16 rb_mbr_reopen(rb_mbr_recovered *out, const rb_mbr_witness *w,
                     const rb_mbr_restart_source *s)
{
    rb_u16 rc;
    if (!out) { return RB_REOPEN_PARAMS; }
    clear((rb_u8 *)out, sizeof(*out));
    if (!w || !s || !s->read || !valid_binding(&w->binding) || !valid_commit(&w->commit)) {
        return RB_REOPEN_PARAMS;
    }
    rc = check_carrier(w, s);
    if (!rc) { rc = check_carrier(w, s); }
    if (rc) { return rc; }
    out->binding = w->binding;
    out->generation = w->commit.generation;
    out->issued = w->commit.issued;
    out->approved_revision = w->commit.approved;
    copy_sector(out->original, w->original);
    copy_sector(out->approved, w->approved);
    return RB_REOPEN_OK;
}
