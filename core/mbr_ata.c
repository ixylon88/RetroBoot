#include "mbr_ata.h"
#include "mbr_bytes.h"
#include "mbr_floppy.h"
#include "config.h"

enum { RB_ATA_SOURCE, RB_ATA_RECOVERY };

rb_u16 __cdecl rb_ata_identify_words(rb_u16 channel, rb_u16 *out);
rb_u16 __cdecl rb_ata_read_sector(rb_u16 channel, rb_u16 lba, rb_u8 *out);
rb_u16 __cdecl rb_ata_write_recovery(rb_u16 lba, const rb_u8 *in);

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

static int identify(rb_u16 channel, rb_ata_identity *out, int require_flush)
{
    static rb_u16 w[256]; /* one exclusive PIO operation at a time */
    rb_u16 i;
    rb_u8 checksum = 0;
    clear((rb_u8 *)out, sizeof(*out));
    if (rb_ata_identify_words(channel, w) || (require_flush && (w[83] & 0xd000) != 0x5000)
        || (w[0] & 0x8084) || !(w[49] & 0x0200)
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

int rb_ata_identify(rb_ata_identity *out)
{
    return identify(RB_ATA_SOURCE, out, 0);
}

int rb_ata_identify_recovery(rb_ata_identity *out, int require_flush)
{
    return identify(RB_ATA_RECOVERY, out, require_flush);
}

int rb_ata_decode_enrollment(rb_ata_enrollment *p, const rb_u8 *s)
{
    static const rb_u8 zero[400] = {0};
    rb_u32 checksum = rb_crc32(s, 508);
    int second = equal(s, (const rb_u8 *)"RBTARG03", 8);
    int history = second || equal(s, (const rb_u8 *)"RBTARG02", 8);
    rb_u16 used = second ? 192 : (history ? 124 : 108);
    clear((rb_u8 *)p, sizeof(*p));
    if ((!history && !equal(s, (const rb_u8 *)"RBTARG01", 8))
        || !equal(s + used, zero, 508 - used)
        || !equal(s + 508, (const rb_u8 *)&checksum, 4)) { return 0; }
    if (second) {
        copy_bytes(p->recovery.serial, s + 124, 20);
        copy_bytes(p->recovery.model, s + 144, 40);
        copy_bytes((rb_u8 *)&p->recovery.sectors_low, s + 184, 4);
        copy_bytes((rb_u8 *)&p->recovery.sectors_high, s + 188, 4);
        if (!printable(p->recovery.serial, 20) || !printable(p->recovery.model, 40)
            || p->recovery.sectors_high > 0xffffUL
            || (!p->recovery.sectors_high && p->recovery.sectors_low < 7)
            || (equal(s + 48, s + 124, 20) && equal(s + 68, s + 144, 40))) { return 0; }
    }
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

static int matches(rb_u16 channel, const rb_ata_identity *expected, int writing)
{
    rb_ata_identity live;
    return identify(channel, &live, writing)
        && equal((const rb_u8 *)&live, (const rb_u8 *)expected, sizeof(live));
}

int __cdecl rb_ata_target_matches(void *profile)
{
    const rb_ata_enrollment *p = (const rb_ata_enrollment *)profile;
    return matches(RB_ATA_SOURCE, &p->device, 0);
}

static int read_bound(rb_u16 channel, const rb_ata_identity *expected, rb_u16 lba, rb_u8 *out)
{
    return matches(channel, expected, 0) && !rb_ata_read_sector(channel, lba, out)
        && matches(channel, expected, 0);
}

rb_u16 __cdecl rb_ata_read_mbr(rb_mbr_target *actual, rb_u8 *out, void *opaque)
{
    const rb_ata_enrollment *p = (const rb_ata_enrollment *)opaque;
    if (!read_bound(RB_ATA_SOURCE, &p->device, 0, out)) {
        clear(out, 512);
        clear((rb_u8 *)actual, sizeof(*actual));
        return 0;
    }
    *actual = p->binding.target;
    return 512;
}

int rb_ata_recovery_label(const rb_ata_enrollment *p)
{
    static rb_u8 label[512];
    return read_bound(RB_ATA_RECOVERY, &p->recovery, 0, label)
        && rb_mbr_label_matches(label, p->binding.recovery_id);
}

int __cdecl rb_ata_pair_matches(void *profile)
{
    return rb_ata_target_matches(profile) && rb_ata_recovery_label((const rb_ata_enrollment *)profile);
}

rb_u16 __cdecl rb_ata_read_record(rb_u16 n, rb_u8 *out, rb_u8 *id, void *profile)
{
    const rb_ata_enrollment *p = (const rb_ata_enrollment *)profile;
    if (n >= 6 || !rb_ata_recovery_label(p) || !read_bound(RB_ATA_RECOVERY, &p->recovery, n + 1, out)
        || !rb_ata_recovery_label(p)) {
        clear(out, 512); clear(id, 16); return 0;
    }
    copy_bytes(id, p->binding.recovery_id, 16);
    return 512;
}

rb_u16 __cdecl rb_ata_write_record(rb_u16 n, const rb_u8 *in, const rb_u8 *id, void *profile)
{
    const rb_ata_enrollment *p = (const rb_ata_enrollment *)profile;
    if (n >= 6 || !equal(id, p->binding.recovery_id, 16) || !rb_ata_recovery_label(p)
        || !matches(RB_ATA_RECOVERY, &p->recovery, 1) || rb_ata_write_recovery(n + 1, in)
        || !rb_ata_recovery_label(p)) { return 0; }
    return 512;
}
