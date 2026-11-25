#include "dos_records.h"

/* Retain the two exact records across the user's decision. Keep these
   buffers in BSS so nested real-mode FAT/partition reads keep their stack. */
rb_dos_workspace rb_dos_buffers;
static rb_dos_record_pair * const reviewed = &rb_dos_buffers.single[0];
static rb_dos_record_pair * const current = &rb_dos_buffers.single[1];

static rb_u32 dword(const rb_u8 *p)
{
    return (rb_u32)p[0] | ((rb_u32)p[1] << 8) | ((rb_u32)p[2] << 16) | ((rb_u32)p[3] << 24);
}

static void put32(rb_u8 *p, rb_u32 value)
{
    rb_u16 i;
    for (i = 0; i < 4; ++i) { p[i] = (rb_u8)value; value >>= 8; }
}

static rb_u16 equal(const void *left, const void *right, rb_u16 count)
{
    const rb_u8 *a = (const rb_u8 *)left, *b = (const rb_u8 *)right;
    while (count) { --count; if (a[count] != b[count]) { return 0; } }
    return 1;
}

rb_u16 rb_dos_config_pair_valid(const rb_u8 *a, const rb_u8 *b, rb_u16 selected)
{
    rb_u32 newer = dword((selected ? b : a) + 16), older = dword((selected ? a : b) + 16);
    return newer - older <= 1 && equal(a, b, 16) && equal(a + 20, b + 20, 18)
        && equal(a + 40, b + 40, 468);
}

void rb_countdown_open(rb_countdown_edit *edit, const rb_dos_choice *choice,
                       const rb_loader_snapshot *snapshot)
{
    const rb_u8 *a = reviewed->copies[0], *b = reviewed->copies[1], *source;
    edit->status = rb_dos_observe(reviewed, &choice->profiles[0], snapshot, 0);
    if (edit->status) { return; }
    edit->target = 1 - reviewed->source;
    source = reviewed->copies[reviewed->source];
    if (!rb_dos_config_pair_valid(a, b, reviewed->source)) {
        edit->status = RB_TIMER_RECORDS;
        return;
    }
    edit->lba = reviewed->lba[edit->target];
    edit->seconds = edit->saved = source[38];
}

static rb_u16 publish(rb_u8 *next, rb_u16 target)
{
    put32(next + 508, rb_crc32(next, 508));
    reviewed->source = target;
    return rb_dos_write_record(current->lba[target], next);
}

void rb_countdown_save(rb_countdown_edit *edit, const rb_dos_choice *choice,
                       const rb_loader_snapshot *snapshot)
{
    rb_u8 *next;
    const rb_u8 *old;
    rb_u16 i, target = 1 - reviewed->source;
    rb_u32 generation;
    if (edit->status || edit->seconds > 60) { return; }
    if (rb_dos_observe(current, &choice->profiles[0], snapshot, 0) || !equal(reviewed, current, sizeof(*current))) {
        edit->status = RB_TIMER_CHANGED;
        return;
    }
    if (edit->seconds == edit->saved) { edit->status = RB_TIMER_UNCHANGED; return; }
    old = reviewed->copies[reviewed->source];
    generation = dword(old + 16);
    if (generation == 0xFFFFFFFFUL) { edit->status = RB_TIMER_FULL; return; }

    /* Build the expected post-write pair from the freshly confirmed pair. */
    next = reviewed->copies[target];
    for (i = 0; i < 512; ++i) { next[i] = old[i]; }
    put32(next + 16, generation + 1);
    next[38] = (rb_u8)edit->seconds;
    if (publish(next, target)) {
        edit->status = RB_TIMER_WRITE;
        return;
    }
    if (rb_dos_observe(current, &choice->profiles[0], snapshot, 0) || !equal(reviewed, current, sizeof(*current))) {
        edit->status = RB_TIMER_READBACK;
        return;
    }
    edit->saved = edit->seconds;
}

rb_u16 rb_trial_open(rb_trial_review *review, rb_handoff_buffer *boot, const rb_dos_choice *choice,
                     const rb_loader_snapshot *snapshot)
{
    const rb_u8 *hold, *prior;
    rb_u16 result = rb_dos_observe(reviewed, &choice->profiles[0], snapshot, boot);
    review->armed = 0;
    if (result) { return result; }
    review->target = 1 - reviewed->source;
    hold = reviewed->copies[reviewed->source]; prior = reviewed->copies[review->target];
    review->generation = dword(hold + 16);
    review->lba = reviewed->lba[review->target];
    /* Only the intact READY record immediately preceding the explicit hold
       can supply a boot-sector witness. Normal selection still selects the hold. */
    if (hold[83] != RB_INSTALL_RECOVERY || prior[83] != RB_INSTALL_READY
            || review->generation - dword(prior + 16) != 1 || !equal(hold, prior, 16)
            || !equal(hold + 20, prior + 20, 63) || !equal(hold + 88, prior + 88, 420)) {
        return RB_TRIAL_HISTORY;
    }
    if (review->generation == 0xFFFFFFFFUL) { return RB_TIMER_FULL; }
    review->vbr_crc = dword(prior + 84);
    if (rb_crc32(boot->sector, 512) != review->vbr_crc) { return RB_TRIAL_VBR; }
    review->armed = 1;
    return RB_TIMER_OK;
}

rb_u16 rb_trial_start(rb_trial_review *review, const rb_handoff_buffer *boot, const rb_dos_choice *choice,
                      const rb_loader_snapshot *snapshot)
{
    rb_handoff_buffer actual;
    rb_u16 i, target = 1 - reviewed->source;
    const rb_u8 *hold = reviewed->copies[reviewed->source];
    rb_u8 *next = reviewed->copies[target];
    if (!review->armed) { return RB_TIMER_CHANGED; }
    review->armed = 0;
    if (rb_dos_observe(current, &choice->profiles[0], snapshot, &actual)
            || !equal(reviewed, current, sizeof(*current)) || !equal(boot, &actual, sizeof(actual))) {
        return RB_TIMER_CHANGED;
    }
    /* Consume the single trial before handoff. A reset leaves verification
       pending even if power fails after this write and before the jump. */
    for (i = 0; i < 512; ++i) { next[i] = hold[i]; }
    put32(next + 16, dword(hold + 16) + 1);
    next[83] = RB_INSTALL_VERIFY;
    if (publish(next, target)) { return RB_TIMER_WRITE; }
    if (rb_dos_observe(current, &choice->profiles[0], snapshot, &actual)
            || !equal(reviewed, current, sizeof(*current)) || !equal(boot, &actual, sizeof(actual))) {
        return RB_TIMER_READBACK;
    }
    rb_video_console();
    rb_handoff(&actual);
    return RB_TIMER_OK;
}
