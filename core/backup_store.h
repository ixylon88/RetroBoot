/* Shared, synchronous access to the enrolled external backup and its witness. */
#ifndef RB_BACKUP_STORE_H
#define RB_BACKUP_STORE_H

#include "backup_verify.h"
#include "backup_boot.h"
#include "mbr_ata.h"

enum { STORE_LAYOUT = 7, STORE_COMMIT = 8, STORE_DATA = 16 };
enum { RB_STORE_INVALID, RB_STORE_EMPTY, RB_STORE_OCCUPIED };

typedef struct {
    rb_ata_enrollment profile;
    rb_mbr_witness witness;
    rb_backup_history history;
    rb_backup_input source;
    rb_u32 limit, sectors;
    rb_u8 block[512], metadata[512];
} rb_backup_store;

/* One boot-time operation owns these buffers. A fresh open binds the floppy,
   carrier and source callbacks anew. A saved file never supplies target LBAs. */
extern rb_backup_store rb_store;
int rb_store_open(rb_u16 drive);
int rb_store_probe_source(void);
int rb_store_history_valid(void);
int rb_store_empty_slot(void);
void rb_store_make_commit(rb_u8 *out, const rb_u32 digest[2]);
rb_u16 __cdecl rb_store_file_read(rb_u32 pos, rb_u8 *out, void *opaque);
/* The decoded claims are valid until the next saved-file check. */
const rb_backup *rb_store_verify(void);

void rb_store_copy(rb_u8 *out, const rb_u8 *in, rb_u16 size);
rb_u32 rb_store_get32(const rb_u8 *p);

#endif
