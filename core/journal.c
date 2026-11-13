#include "journal.h"

static rb_u16 word(const rb_u8 *p) { return p[0] | ((rb_u16)p[1] << 8); }
static rb_u32 dword(const rb_u8 *p) { return (rb_u32)word(p) | ((rb_u32)word(p + 2) << 16); }
static void clear(void *p, rb_u16 n)
{
    rb_u8 *bytes = (rb_u8 *)p;
    while (n) { bytes[--n] = 0; }
}
static rb_u16 zeros(const rb_u8 *p, rb_u16 n)
{
    while (n) { if (p[--n]) { return 0; } } return 1;
}
static rb_u16 same(const rb_u8 *a, const rb_u8 *b, rb_u16 n)
{
    while (n) { --n; if (a[n] != b[n]) { return 0; } } return 1;
}
static rb_u16 visible(rb_u16 type)
{
    switch (type) {
    case 6: case 14: case 11: case 12: case 7: return type;
    case 0x16: case 0x1E: case 0x1B: case 0x1C: case 0x17: return type - 0x10;
    default: return 0;
    }
}

static rb_u16 geometry(const rb_journal_context *c)
{
    rb_u32 track;
    if (!c->capacity_low && !c->capacity_high) { return 0; }
    if (c->io_mode == 1) { return !c->heads && !c->sectors_per_track; }
    if (c->io_mode != 2 || c->capacity_high || !c->heads || c->heads > 256
            || !c->sectors_per_track || c->sectors_per_track > 63) { return 0; }
    track = (rb_u32)c->heads * c->sectors_per_track;
    return c->capacity_low <= track * 1024UL && c->capacity_low % track == 0;
}

/* The caller's validated scan supplies structural/EBR bounds. A journal only
 * changes visibility: each snapshot must retain that exact primary layout. */
static rb_u16 snapshot(const rb_u8 *mbr, const rb_journal_context *c, rb_u16 intended)
{
    const rb_partition *p;
    const rb_u8 *entry;
    rb_u16 i, type, active = 0;
    if (mbr[510] != 0x55 || mbr[511] != 0xAA || dword(mbr + 440) != c->scan->disk_id
            || mbr[432] != 'R' || mbr[433] != 'B' || mbr[434] != 'M' || mbr[435] != '1'
            || dword(mbr + 436) != c->scan->entries[c->admin_index].start) { return 0; }
    for (i = 0; i < 4; ++i) {
        p = &c->scan->entries[i]; entry = mbr + 446 + i * 16;
        if (p->logical || p->slot != i + 1 || p->table_lba) { return 0; }
        if (!p->type) { if (!zeros(entry, 16)) { return 0; } continue; }
        if ((entry[0] != 0 && entry[0] != 0x80) || dword(entry + 8) != p->start
                || dword(entry + 12) != p->sectors) { return 0; }
        type = visible(p->type);
        if (type) {
            if (visible(entry[4]) != type || (intended && entry[0] && entry[4] != type)) { return 0; }
        } else if ((p->type != 5 && p->type != 15) || entry[4] != p->type || entry[0]) { return 0; }
        if (entry[0] && ++active > 1) { return 0; }
    }
    return !intended || active == 1;
}

rb_u16 rb_journal_decode(rb_journal_record *r, const rb_u8 *data,
                         rb_u16 length, const rb_journal_context *c)
{
    const rb_u8 magic[8] = {'R','B','T','X','N',0,0,0};
    const rb_partition *admin;
    rb_u16 i, j, phase, allowed, changed = 0;
    rb_u32 sequence;
    clear(r, sizeof(*r));
    if (length != RB_JOURNAL_BYTES) { return RB_JOURNAL_FORMAT; }
    phase = word(data + 36); sequence = dword(data + 16);
    if (!same(data, magic, 8) || word(data + 8) != 1 || word(data + 10) != 512
            || dword(data + 12) != RB_JOURNAL_BYTES || !sequence || phase > RB_TX_COMMITTED
            || (phase == RB_TX_EMPTY ? sequence != 1 : sequence < 2)
            || !zeros(data + 76, 432) || zeros(data + 48, 16)) { return RB_JOURNAL_FORMAT; }
    if (rb_crc32(data, 508) != dword(data + 508)
            || rb_crc32(data + 512, 512) != dword(data + 64)
            || rb_crc32(data + 1024, 512) != dword(data + 68)) { return RB_JOURNAL_CRC; }
    if (c->scan->status || c->scan->count < 5 || c->scan->count > RB_SCAN_PARTITIONS
            || c->scan->ebr_count > RB_SCAN_EBRS || c->admin_index < 4
            || c->admin_index >= c->scan->count || !c->scan->disk_id || zeros(c->media_id, 16)) {
        return RB_JOURNAL_IDENTITY;
    }
    admin = &c->scan->entries[c->admin_index];
    if (!admin->logical || (admin->type != 0x16 && admin->type != 0x1E)
            || !admin->start || !admin->sectors || admin->sectors - 1 > 0xFFFFFFFFUL - admin->start
            || (c->capacity_high == 0 && admin->start + (admin->sectors - 1) >= c->capacity_low)
            || dword(data + 20) != c->scan->disk_id || dword(data + 24) != rb_layout_crc(c->scan)
            || dword(data + 28) != admin->start || dword(data + 32) != admin->sectors
            || !same(data + 48, c->media_id, 16)) { return RB_JOURNAL_IDENTITY; }
    if (!geometry(c) || word(data + 38) != c->io_mode || dword(data + 40) != c->capacity_low
            || dword(data + 44) != c->capacity_high || word(data + 72) != c->heads
            || word(data + 74) != c->sectors_per_track) { return RB_JOURNAL_GEOMETRY; }
    if (!snapshot(data + 512, c, 0) || !snapshot(data + 1024, c, phase != RB_TX_EMPTY)) {
        return RB_JOURNAL_MBR;
    }
    for (i = 0; i < 512; ++i) {
        if (data[512 + i] == data[1024 + i]) { continue; }
        allowed = 0;
        for (j = 0; j < 4; ++j) {
            if (visible(c->scan->entries[j].type) && (i == 446 + j * 16 || i == 450 + j * 16)) {
                allowed = 1; changed |= 1U << j;
            }
        }
        if (!allowed) { return RB_JOURNAL_DELTA; }
    }
    if (phase == RB_TX_EMPTY ? changed != 0 : changed == 0) { return RB_JOURNAL_DELTA; }
    r->sequence = sequence; r->phase = phase; r->changed = changed;
    r->before_crc = dword(data + 64); r->after_crc = dword(data + 68);
    return RB_JOURNAL_OK;
}

void rb_journal_inspect(rb_journal_result *r, const rb_u8 *a, const rb_u8 *b,
                        rb_u16 mask, const rb_journal_context *c, const rb_u8 *current)
{
    rb_journal_record records[2];
    const rb_u8 *chosen, *older;
    rb_u16 pick, old;
    clear(r, sizeof(*r)); r->source = RB_JOURNAL_NONE;
    if (mask & ~3U) {
        r->status = RB_JOURNAL_UNAVAILABLE;
        r->copies[0] = r->copies[1] = RB_JOURNAL_FORMAT; return;
    }
    r->copies[0] = mask & 1 ? rb_journal_decode(&records[0], a, RB_JOURNAL_BYTES, c) : RB_JOURNAL_MISSING;
    r->copies[1] = mask & 2 ? rb_journal_decode(&records[1], b, RB_JOURNAL_BYTES, c) : RB_JOURNAL_MISSING;
    if (r->copies[0] || r->copies[1]) {
        r->status = r->copies[0] && r->copies[1] ? RB_JOURNAL_UNAVAILABLE : RB_JOURNAL_DEGRADED; return;
    }
    r->status = RB_JOURNAL_CONFLICT;
    if (records[0].sequence == records[1].sequence) {
        if (records[0].phase == records[1].phase) {
            if (!same(a, b, RB_JOURNAL_BYTES)) { return; }
            pick = 0;
        } else {
            /* Completion is in the other slot, for this exact prepared pair. */
            if (records[0].phase + records[1].phase != RB_TX_PREPARED + RB_TX_COMMITTED
                    || !same(a + 512, b + 512, 1024)) { return; }
            pick = records[1].phase == RB_TX_COMMITTED;
        }
    } else {
        pick = records[1].sequence > records[0].sequence; old = 1 - pick;
        chosen = pick ? b : a; older = old ? b : a;
        if (records[pick].phase != RB_TX_PREPARED || records[old].phase == RB_TX_PREPARED
                || records[old].sequence == 0xFFFFFFFFUL
                || records[pick].sequence != records[old].sequence + 1
                || !same(older + 1024, chosen + 512, 512)) { return; }
    }
    chosen = pick ? b : a;
    r->record = records[pick]; r->source = pick; r->status = RB_JOURNAL_OK;
    r->observation = RB_TX_DIVERGED;
    if (same(current, chosen + 1024, 512)) {
        r->observation = r->record.phase == RB_TX_EMPTY ? RB_TX_BASELINE
            : r->record.phase == RB_TX_COMMITTED ? RB_TX_COMMITTED_NEW : RB_TX_PREPARED_NEW;
    } else if (r->record.phase == RB_TX_PREPARED && same(current, chosen + 512, 512)) {
        r->observation = RB_TX_PREPARED_OLD;
    }
}
