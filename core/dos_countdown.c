#include "dos_countdown.h"

/* Retain the two exact records across the user's decision. Keep these
   buffers in BSS so nested real-mode FAT/partition reads keep their stack. */
static rb_countdown_pair reviewed, current;

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

void rb_countdown_open(rb_countdown_edit *edit, const rb_dos_choice *choice,
                       const rb_loader_snapshot *snapshot)
{
    const rb_u8 *a = reviewed.copies[0], *b = reviewed.copies[1], *source;
    rb_u32 newer, older;
    edit->status = rb_countdown_observe(&reviewed, choice, snapshot);
    if (edit->status) { return; }
    edit->target = 1 - reviewed.source;
    source = reviewed.copies[reviewed.source];
    newer = dword(source + 16);
    older = dword(reviewed.copies[edit->target] + 16);
    /* Same two healthy generations the external editor can advance/recover. */
    if (newer - older > 1 || !equal(a, b, 16) || !equal(a + 20, b + 20, 18)
            || !equal(a + 40, b + 40, 468)) {
        edit->status = RB_TIMER_RECORDS;
        return;
    }
    edit->lba = reviewed.lba[edit->target];
    edit->seconds = edit->saved = source[38];
}

void rb_countdown_save(rb_countdown_edit *edit, const rb_dos_choice *choice,
                       const rb_loader_snapshot *snapshot)
{
    rb_u8 *next;
    const rb_u8 *old;
    rb_u16 i, target = 1 - reviewed.source;
    rb_u32 generation;
    if (edit->status || edit->seconds > 60) { return; }
    if (rb_countdown_observe(&current, choice, snapshot) || !equal(&reviewed, &current, sizeof(current))) {
        edit->status = RB_TIMER_CHANGED;
        return;
    }
    if (edit->seconds == edit->saved) { edit->status = RB_TIMER_UNCHANGED; return; }
    old = reviewed.copies[reviewed.source];
    generation = dword(old + 16);
    if (generation == 0xFFFFFFFFUL) { edit->status = RB_TIMER_FULL; return; }

    /* Build the expected post-write pair from the freshly confirmed pair. */
    next = reviewed.copies[target];
    for (i = 0; i < 512; ++i) { next[i] = old[i]; }
    put32(next + 16, generation + 1);
    next[38] = (rb_u8)edit->seconds;
    put32(next + 508, rb_crc32(next, 508));
    reviewed.source = target;
    if (rb_dos_write_config(current.lba[target], next)) {
        edit->status = RB_TIMER_WRITE;
        return;
    }
    if (rb_countdown_observe(&current, choice, snapshot) || !equal(&reviewed, &current, sizeof(current))) {
        edit->status = RB_TIMER_READBACK;
        return;
    }
    edit->saved = edit->seconds;
}
