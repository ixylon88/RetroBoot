#ifndef RB_ADMIN_AUDIT_H
#define RB_ADMIN_AUDIT_H

#include "volume.h"

#define RB_AUDIT_FILES 8U
/* At 512 bytes/cluster: 8 KiB bootstrap + 48 KiB Stage 2 + four records
 * and two three-sector journal records. */
#define RB_AUDIT_NODES 122U

enum {
    RB_AUDIT_OK, RB_AUDIT_SCAN, RB_AUDIT_ADMIN, RB_AUDIT_IO,
    RB_AUDIT_ROOT, RB_AUDIT_CHAIN, RB_AUDIT_SHARED, RB_AUDIT_COPIES,
    RB_AUDIT_HEADER, RB_AUDIT_ORPHAN, RB_AUDIT_CHANGED, RB_AUDIT_BOOTSTRAP
};

typedef struct {
    rb_u32 bytes, first_lba;
    rb_u16 first_cluster, clusters;
} rb_audit_file;

typedef struct {
    rb_u16 status, detail, error_file, error_cluster;
    rb_u32 error_lba;
    rb_u16 total_clusters, used_clusters, free_clusters;
    rb_audit_file files[RB_AUDIT_FILES];
    rb_partition_scan scan;
    rb_u32 journal_lba[2][3];
} rb_admin_audit;

extern const char * const rb_audit_names[RB_AUDIT_FILES];

/* Read-only observation of the current eight-file management format. Unknown
 * live root entries are unsupported. File contents are not authenticated;
 * success is not persistent ownership, a write lease or OS authorization.
 * Private static scratch keeps the synchronous C16 call below its stack limit;
 * this function is deliberately non-reentrant. Failure clears all file data,
 * the scan and journal-sector map. The map handles fragmented journal chains. */
rb_u16 rb_audit_admin(rb_admin_audit *result, rb_sector_reader read, void *opaque,
                      rb_u32 low, rb_u32 high, rb_u32 disk_id, rb_u32 admin_lba);
rb_u16 __cdecl rb_audit_selftest(void);

#endif
