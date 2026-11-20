#include "mbr_ata.h"
#include "mbr_bytes.h"
#include "config.h"

rb_u16 __cdecl rb_ata_identify_words(rb_u16 *out);
rb_u16 __cdecl rb_ata_sector_zero(rb_u8 *out);

static int printable(const rb_u8 *s, rb_u16 n)
{
    int present = 0;
    while (n--) {
        if (*s < ' ' || *s > '~') { return 0; }
        if (*s++ != ' ') { present = 1; }
    }
    return present;
}

static void copy_bytes(rb_u8 *out, const rb_u8 *in, rb_u16 count)
{
    while (count--) { *out++ = *in++; }
}

static void ata_string(rb_u8 *out, const rb_u16 *words, rb_u16 count)
{
    while (count--) {
        *out++ = (rb_u8)(*words >> 8);
        *out++ = (rb_u8)*words++;
    }
}

static rb_u32 doubleword(const rb_u16 *w)
{
    return w[0] | ((rb_u32)w[1] << 16);
}

int rb_ata_identify(rb_ata_identity *out)
{
    rb_u16 w[256], i;
    rb_u8 checksum = 0;
    clear((rb_u8 *)out, sizeof(*out));
    if (rb_ata_identify_words(w) || (w[0] & 0x8084) || !(w[49] & 0x0200)
        || ((w[106] & 0xc000) == 0x4000 && (w[106] & 0x1000))) { return 0; }
    if ((rb_u8)w[255] == 0xa5) {
        for (i = 0; i < 256; ++i) { checksum += (rb_u8)w[i] + (rb_u8)(w[i] >> 8); }
        if (checksum) { return 0; }
    }
    ata_string(out->serial, w + 10, 10);
    ata_string(out->model, w + 27, 20);
    if ((w[83] & 0xc400) == 0x4400) {
        out->sectors_low = doubleword(w + 100);
        out->sectors_high = doubleword(w + 102);
        if (out->sectors_high > 0xffffUL) { return 0; }
    } else {
        out->sectors_low = doubleword(w + 60);
        if (out->sectors_low > 0x0fffffffUL) { return 0; }
    }
    return (out->sectors_low || out->sectors_high) && printable(out->serial, 20)
        && printable(out->model, 40);
}

int rb_ata_decode_enrollment(rb_ata_enrollment *p, const rb_u8 *s)
{
    static const rb_u8 zero[400] = {0};
    rb_u32 checksum = rb_crc32(s, 508);
    int history = equal(s, (const rb_u8 *)"RBTARG02", 8);
    if ((!history && !equal(s, (const rb_u8 *)"RBTARG01", 8))
        || !equal(s + (history ? 124 : 108), zero, history ? 384 : 400)
        || !equal(s + 508, (const rb_u8 *)&checksum, 4)) { return 0; }
    copy_bytes(p->witness_id, s + 108, 16);
    copy_bytes(p->binding.target.id, s + 8, 16);
    copy_bytes((rb_u8 *)&p->binding.target.capacity_low, s + 24, 4);
    copy_bytes((rb_u8 *)&p->binding.target.capacity_high, s + 28, 4);
    copy_bytes(p->binding.recovery_id, s + 32, 16);
    copy_bytes(p->device.serial, s + 48, 20);
    copy_bytes(p->device.model, s + 68, 40);
    p->device.sectors_low = p->binding.target.capacity_low;
    p->device.sectors_high = p->binding.target.capacity_high;
    return (history ? valid_witness_binding(&p->binding, p->witness_id) : valid_binding(&p->binding))
        && p->device.sectors_high <= 0xffffUL
        && printable(p->device.serial, 20) && printable(p->device.model, 40);
}

int __cdecl rb_ata_target_matches(void *profile)
{
    const rb_ata_enrollment *p = (const rb_ata_enrollment *)profile;
    rb_ata_identity live;
    return rb_ata_identify(&live) && equal((const rb_u8 *)&live, (const rb_u8 *)&p->device, sizeof(live));
}

rb_u16 __cdecl rb_ata_read_mbr(rb_mbr_target *actual, rb_u8 *out, void *opaque)
{
    const rb_ata_enrollment *p = (const rb_ata_enrollment *)opaque;
    if (!rb_ata_target_matches(opaque) || rb_ata_sector_zero(out) || !rb_ata_target_matches(opaque)) {
        clear(out, 512);
        clear((rb_u8 *)actual, sizeof(*actual));
        return 0;
    }
    *actual = p->binding.target;
    return 512;
}
