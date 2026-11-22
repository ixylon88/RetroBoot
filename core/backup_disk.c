/* Publish a verified snapshot on the enrolled secondary IDE disk. */
#include "backup_store.h"
#include "fingerprint.h"
#include "mbr_console.h"
#include "rescue_text.h"

rb_u16 __cdecl rb_ata_store_write(rb_u16 lba, const rb_u8 *in);
static rb_u32 written, digest[2];

static rb_u16 __cdecl stage(rb_u32 pos, const rb_u8 *in, void *opaque)
{
    (void)opaque;
    if (pos != written || pos >= rb_store.sectors || rb_store.sectors > rb_store.limit || !rb_store_empty_slot()
        || rb_ata_store_write((rb_u16)(STORE_DATA + pos), in)) { return 1; }
    rb_fingerprint_sector(digest, pos, in);
    ++written;
    return 0;
}

static rb_u16 __cdecl reopen(rb_u32 *bytes, void *opaque)
{
    (void)opaque;
    if (written != rb_store.sectors || !rb_store_empty_slot() || rb_store_file_read(0, rb_store.metadata, (void *)0)) { return 1; }
    *bytes = rb_store_get32(rb_store.metadata + 12);
    return 0;
}

static rb_u32 collect(rb_backup *b)
{
    rb_backup_payloads capture;
    rb_backup_plan *p = &capture.plan;
    rb_u16 i;
    rb_u32 pos = 7;
    rb_backup_payload_capture(&capture, &rb_store.source.device, rb_store.source.read, (void *)0);
    if (p->status || !p->count || p->count >= RB_BACKUP_MAX) { return 0; }
    for (i = 0; i < sizeof(*b); ++i) { ((rb_u8 *)b)[i] = 0; }
    b->generation = 1; /* This dedicated slot accepts one completed snapshot. */
    b->disk_id = p->observed.disk_id; b->layout_crc = p->observed.layout_crc;
    b->admin_start = p->observed.admin_start; b->admin_sectors = p->observed.admin_sectors;
    rb_store_copy(b->media_id, p->observed.media_id, 16);
    b->capacity_low = p->device.capacity_low; b->capacity_high = p->device.capacity_high;
    b->count = p->count + 1; b->route = 1;
    b->heads = p->device.heads; b->sectors_per_track = p->device.sectors_per_track;
    for (i = 0; i < 2; ++i) {
        b->entries[i].kind = i + 1; b->entries[i].sectors = 1;
        b->entries[i].file_sector = 5 + i;
    }
    b->entries[0].crc = rb_store.witness.commit.original_crc;
    b->entries[1].crc = rb_store.witness.commit.approved_crc;
    for (i = 1; i < p->count; ++i) {
        const rb_capture_extent *live = &p->entries[i];
        rb_backup_extent *e = &b->entries[i + 1];
        e->kind = live->kind; e->index = live->index; e->lba = live->lba;
        e->owner_start = live->owner_start; e->owner_sectors = live->owner_sectors;
        e->sectors = live->sectors; e->file_sector = pos; e->crc = capture.crc[i]; pos += live->sectors;
    }
    return pos == p->estimated_container_sectors ? pos : 0;
}

static int publish(void)
{
    rb_backup claims;
    static const rb_backup_destination destination = {stage, reopen, rb_store_file_read, (void *)0};
    rb_backup_verified result;
    if (!rb_store_probe_source()) { line(RB_RS_STORE_SOURCE); return 0; }
    rb_store.sectors = collect(&claims);
    if (!rb_store.sectors) { line(RB_RS_STORE_SOURCE); return 0; }
    if (rb_store.sectors > rb_store.limit || !rb_store_empty_slot()) { line(RB_RS_STORE_MEDIA); return 0; }
    written = digest[0] = digest[1] = 0;
    if (rb_backup_verify_live(&result, &claims, rb_store.sectors, &rb_store.source, &rb_store.history, &destination)
        || result.sectors != rb_store.sectors || result.approved_revision != rb_store.witness.commit.approved
        || rb_mbr_verify_witness(&rb_store.witness, rb_store.profile.witness_id, &rb_store.history.witness)
        || rb_mbr_verify_carrier(&rb_store.witness, &rb_store.history.carrier) || !rb_store_empty_slot()) { return 0; }
    rb_store_make_commit(rb_store.metadata, digest);
    if (rb_ata_store_write(STORE_COMMIT, rb_store.metadata)) { return 0; }
    return rb_store_verify() != (const rb_backup *)0;
}

rb_u16 __cdecl rb_backup_disk_run(rb_u16 boot_drive)
{
    int slot;
    rb_u16 key;
    line("RB BACKUP DISK");
    line(RB_RS_STORE_MENU);
    do { key = rb_console_key(); } while (key != 'S' && key != 'V' && key != 27);
    if (key == 27) { line(RB_RS_STORE_CANCEL); return 0; }
    slot = rb_store_open(boot_drive);
    if (slot == RB_STORE_INVALID) { line(RB_RS_STORE_MEDIA); return 1; }
    if (key == 'V' && slot == RB_STORE_EMPTY) { line(RB_RS_STORE_EMPTY); return 1; }
    if (key == 'S' && slot != RB_STORE_EMPTY) { line(RB_RS_STORE_USED); return 1; }
    line(key == 'S' ? RB_RS_STORE_SAVE : RB_RS_STORE_VERIFY);
    if (key == 'S' && !rb_store_history_valid()) { line(RB_RS_STORE_HISTORY); return 1; }
    if (!(key == 'S' ? publish() : rb_store_verify() != (const rb_backup *)0)) { line(RB_RS_STORE_FAILED); return 1; }
    line(key == 'S' ? RB_RS_STORE_DONE : RB_RS_STORE_READ);
    count(RB_RS_VERIFY_COUNT, rb_store.sectors); count(RB_RS_STORE_REV, rb_store.witness.commit.approved);
    return 0;
}
