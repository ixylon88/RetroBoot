#include "journal_io.h"
#include "admin_audit.h"
#include "state.h"

static struct {
    rb_admin_audit audit;
    rb_u8 records[2][RB_JOURNAL_BYTES], mbr[512], sector[512];
    rb_config_result config;
    rb_state_result state;
    rb_journal_context context;
    rb_sector_reader read;
    void *opaque;
} work;

static void clear(void *p, rb_u16 n)
{
    rb_u8 *bytes = (rb_u8 *)p;
    while (n) { bytes[--n] = 0; }
}
static rb_u16 same(const rb_u8 *a, const rb_u8 *b, rb_u16 n)
{
    while (n) { --n; if (a[n] != b[n]) { return 0; } } return 1;
}
static rb_u16 __cdecl capture(rb_u32 lba, rb_u8 *sector, void *opaque)
{
    rb_u16 i, code;
    (void)opaque;
    code = work.read(lba, sector, work.opaque);
    if (!code && !lba) { for (i = 0; i < 512; ++i) { work.mbr[i] = sector[i]; } }
    return code;
}
static void fail(rb_journal_diagnosis *r, rb_u16 status, rb_u16 detail, rb_u32 lba)
{
    clear(r, sizeof(*r));
    r->status = status; r->detail = detail; r->error_lba = lba;
    r->journal.status = RB_JOURNAL_UNAVAILABLE; r->journal.source = RB_JOURNAL_NONE;
    r->journal.copies[0] = r->journal.copies[1] = RB_JOURNAL_MISSING;
}

static void load(rb_journal_diagnosis *r, rb_u32 low, rb_u32 high,
                  rb_u32 disk_id, rb_u32 admin_lba, rb_u16 mode, rb_u16 heads, rb_u16 spt)
{
    const rb_partition *admin = (const rb_partition *)0;
    rb_u16 i, copy, mask = 0;
    rb_u32 lba;
    fail(r, RB_JLOAD_OK, 0, 0);
    if (rb_audit_admin(&work.audit, capture, (void *)0, low, high, disk_id, admin_lba)) {
        fail(r, RB_JLOAD_ALLOCATION, work.audit.status, work.audit.error_lba); return;
    }
    work.context.scan = &work.audit.scan;
    for (i = 4; i < work.audit.scan.count; ++i) {
        if (work.audit.scan.entries[i].start == admin_lba) {
            admin = &work.audit.scan.entries[i]; work.context.admin_index = i;
        }
    }
    if (!admin) { fail(r, RB_JLOAD_IDENTITY, 0, admin_lba); return; }
    for (i = 0; i < 4; ++i) {
        lba = work.audit.files[i + 2].first_lba;
        if (work.read(lba, work.records[i % 2], work.opaque)) { fail(r, RB_JLOAD_IO, i + 3, lba); return; }
        if (i == 1) {
            rb_config_select(&work.config, work.records[0], work.records[1], 3, &work.audit.scan, admin);
            if (work.config.status || work.config.copies[0] || work.config.copies[1]) {
                fail(r, RB_JLOAD_CONFIG, work.config.status ? work.config.status
                    : work.config.copies[0] ? work.config.copies[0] : work.config.copies[1],
                    work.config.status == RB_CONFIG_CONFLICT ? 0 : work.audit.files[work.config.copies[0] ? 2 : 3].first_lba); return;
            }
            if (work.config.config.version != 2 || work.records[0][8] != 2 || work.records[1][8] != 2
                    || !same(work.records[0] + 48, work.records[1] + 48, 16)) {
                fail(r, RB_JLOAD_IDENTITY, 1, 0); return;
            }
            for (copy = 0; copy < 16; ++copy) { work.context.media_id[copy] = work.config.config.media_id[copy]; }
        } else if (i == 3) {
            rb_state_select(&work.state, work.records[0], work.records[1], 3, &work.audit.scan, admin);
            if (work.state.status || work.state.copies[0] || work.state.copies[1]) {
                fail(r, RB_JLOAD_STATE, work.state.status ? work.state.status
                    : work.state.copies[0] ? work.state.copies[0] : work.state.copies[1],
                    work.state.status == RB_CONFIG_CONFLICT ? 0 : work.audit.files[work.state.copies[0] ? 4 : 5].first_lba); return;
            }
            if (!same(work.context.media_id, work.records[0] + 48, 16)
                    || !same(work.context.media_id, work.records[1] + 48, 16)) {
                fail(r, RB_JLOAD_IDENTITY, 2, 0); return;
            }
        }
    }
    work.context.capacity_low = low; work.context.capacity_high = high;
    work.context.io_mode = mode; work.context.heads = heads; work.context.sectors_per_track = spt;
    clear(work.records, sizeof(work.records));
    for (copy = 0; copy < 2; ++copy) {
        for (i = 0; i < 3; ++i) {
            lba = work.audit.journal_lba[copy][i];
            if (work.read(lba, work.records[copy] + i * 512, work.opaque)) {
                r->status = RB_JLOAD_IO; r->detail = copy + 7; r->error_lba = lba; break;
            }
        }
        if (i == 3) { mask |= 1U << copy; }
    }
    if (work.read(0, work.sector, work.opaque)) { fail(r, RB_JLOAD_IO, 0, 0); return; }
    if (!same(work.mbr, work.sector, 512)) { fail(r, RB_JLOAD_CHANGED, 0, 0); return; }
    rb_journal_inspect(&r->journal, work.records[0], work.records[1], mask, &work.context, work.mbr);
}

void rb_journal_load(rb_journal_diagnosis *r, rb_sector_reader read, void *opaque,
                     rb_u32 low, rb_u32 high, rb_u32 disk_id, rb_u32 admin_lba,
                     rb_u16 mode, rb_u16 heads, rb_u16 spt)
{
    clear(&work, sizeof(work)); work.read = read; work.opaque = opaque;
    load(r, low, high, disk_id, admin_lba, mode, heads, spt);
    clear(&work, sizeof(work));
}
