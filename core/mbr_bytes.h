/* Shared bounded operations for the native MBR history models. */
#ifndef RB_MBR_BYTES_H
#define RB_MBR_BYTES_H

static int equal(const rb_u8 *a, const rb_u8 *b, rb_u16 size)
{
    rb_u16 i;
    for (i = 0; i < size; ++i) {
        if (a[i] != b[i]) { return 0; }
    }
    return 1;
}

static void clear(rb_u8 *bytes, rb_u16 size)
{
    while (size) { bytes[--size] = 0; }
}

static void copy_sector(rb_u8 *out, const rb_u8 *in)
{
    rb_u16 i;
    for (i = 0; i < 512; ++i) { out[i] = in[i]; }
}

static int same_target(const rb_mbr_target *a, const rb_mbr_target *b)
{
    return equal(a->id, b->id, 16) && a->capacity_low == b->capacity_low
        && a->capacity_high == b->capacity_high;
}

static int same_binding(const rb_mbr_binding *a, const rb_mbr_binding *b)
{
    return same_target(&a->target, &b->target) && equal(a->recovery_id, b->recovery_id, 16);
}

static int valid_binding(const rb_mbr_binding *b)
{
    static const rb_u8 empty[16] = {0};
    return (b->target.capacity_low || b->target.capacity_high)
        && !equal(b->target.id, empty, 16) && !equal(b->recovery_id, empty, 16)
        && !equal(b->target.id, b->recovery_id, 16);
}

#endif
