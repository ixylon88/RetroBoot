/* Console and byte operations for the standalone floppy fixtures. */
#ifndef RB_MBR_FIXTURE_H
#define RB_MBR_FIXTURE_H

static __inline int same(const rb_u8 *a, const rb_u8 *b, rb_u16 n)
{
    while (n) { --n; if (a[n] != b[n]) { return 0; } }
    return 1;
}

static __inline int empty(const void *p, rb_u16 n)
{
    const rb_u8 *b = (const rb_u8 *)p;
    while (n) { if (b[--n]) { return 0; } }
    return 1;
}

static void copy(rb_u8 *out, const rb_u8 *in, rb_u16 n)
{
    while (n) { --n; out[n] = in[n]; }
}

static void print(const char *s)
{
    while (*s) { rb_putc(*s++); }
}

static void line(const char *s)
{
    print(s); rb_putc(13); rb_putc(10);
}

static void count(const char *s, rb_u32 value)
{
    char digits[11];
    rb_u16 i = 10;
    digits[i] = 0;
    do { digits[--i] = (char)('0' + value % 10); value /= 10; } while (value);
    print(s); line(digits + i);
}

#endif
