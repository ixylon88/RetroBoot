#ifndef RB_MBR_COMPARE_H
#define RB_MBR_COMPARE_H

static int equal(const rb_u8 *a, const rb_u8 *b, rb_u16 size)
{
    rb_u16 i;
    for (i = 0; i < size; ++i) {
        if (a[i] != b[i]) { return 0; }
    }
    return 1;
}

static __inline void clear(rb_u8 *bytes, rb_u16 size)
{
    while (size) { bytes[--size] = 0; }
}

#endif
