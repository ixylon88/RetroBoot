#ifndef RB_JOURNAL_H
#define RB_JOURNAL_H

#include "config.h"

#define RB_JOURNAL_BYTES 1536U
#define RB_JOURNAL_NONE 0xFFFFU

enum { RB_TX_EMPTY, RB_TX_PREPARED, RB_TX_COMMITTED };
enum {
    RB_JOURNAL_OK, RB_JOURNAL_MISSING, RB_JOURNAL_FORMAT, RB_JOURNAL_CRC,
    RB_JOURNAL_IDENTITY, RB_JOURNAL_GEOMETRY, RB_JOURNAL_MBR, RB_JOURNAL_DELTA,
    RB_JOURNAL_UNAVAILABLE, RB_JOURNAL_DEGRADED, RB_JOURNAL_CONFLICT
};
enum {
    RB_TX_UNOBSERVED, RB_TX_BASELINE, RB_TX_PREPARED_OLD, RB_TX_PREPARED_NEW,
    RB_TX_COMMITTED_NEW, RB_TX_DIVERGED
};

typedef struct {
    const rb_partition_scan *scan;
    rb_u32 capacity_low, capacity_high;
    rb_u8 media_id[16];
    rb_u16 admin_index, io_mode, heads, sectors_per_track;
} rb_journal_context;

typedef struct {
    rb_u32 sequence, before_crc, after_crc;
    rb_u16 phase, changed;
} rb_journal_record;

typedef struct {
    rb_journal_record record;
    rb_u16 status, copies[2], source, observation;
} rb_journal_result;

/* Pure, bounded record model. Context must come from an independently checked
 * complete layout, management identity and BIOS geometry. It is not discovered
 * or authenticated by this API. Neither result is write or boot authority. */
rb_u16 rb_journal_decode(rb_journal_record *result, const rb_u8 *record,
                         rb_u16 length, const rb_journal_context *context);
/* Each readable slot must supply exactly RB_JOURNAL_BYTES; the current MBR is
 * exactly 512 bytes. No disk access, static scratch or retained input pointers.
 * One damaged/missing copy blocks selection; it never hides a newer attempt. */
void rb_journal_inspect(rb_journal_result *result, const rb_u8 *a, const rb_u8 *b,
                        rb_u16 readable_mask, const rb_journal_context *context,
                        const rb_u8 *current_mbr);
rb_u16 __cdecl rb_journal_selftest(void);

#endif
