#include "fat_plan.h"

typedef struct {
    rb_u32 sectors, expected_clusters;
    rb_u16 type, spc, status;
} boundary;

/* Vectors around the actual BPB cluster-count cutovers, including the
   repository's last supported FAT32 cluster count. No disk I/O. */
static const boundary cases[] = {
    {4149, 0, 0x0E, 1, RB_FORMAT_CLUSTER_COUNT},
    {4150, 4085, 0x0E, 1, RB_FORMAT_OK},
    {4152, 4085, 0x0E, 1, RB_FORMAT_OK},
    {66073UL, 65524UL, 0x1E, 1, RB_FORMAT_OK},
    {66074UL, 0, 0x1E, 1, RB_FORMAT_CLUSTER_COUNT},
    {66580UL, 0, 0x0C, 1, RB_FORMAT_CLUSTER_COUNT},
    {66581UL, 65525UL, 0x0C, 1, RB_FORMAT_OK},
    {66599UL, 65525UL, 0x1C, 1, RB_FORMAT_OK},
    {272696352UL, 268435438UL, 0x0C, 1, RB_FORMAT_OK},
    {272696353UL, 0, 0x0C, 1, RB_FORMAT_CLUSTER_COUNT},
    {1, 0, 0x0E, 1, RB_FORMAT_CLUSTER_COUNT},
    {32, 0, 0x0C, 1, RB_FORMAT_CLUSTER_COUNT},
    {4152, 0, 0x0E, 3, RB_FORMAT_CLUSTER_SIZE},
    {4152, 0, 0x0E, 128, RB_FORMAT_CLUSTER_SIZE},
    {4152, 0, 0x07, 1, RB_FORMAT_TARGET}
};

rb_u16 rb_format_plan_selftest(void)
{
    rb_rescue_device disk = {0x80, 1, 0, 0, 0, 1};
    rb_partition p = {1, 0, 0, 0, 0, 1, 0};
    const rb_u16 geometry[3] = {8, 16, 63};
    const rb_u8 entry[16] = {0};
    rb_fat_plan out;
    rb_u16 i, failures = 0;
    for (i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        const boundary *v = &cases[i];
        p.type = v->type; p.sectors = v->sectors;
        if (rb_plan_primary_fat(&out, &p, entry, &disk, geometry, v->spc) != v->status
                || out.clusters != v->expected_clusters || (!v->expected_clusters && out.fat1)) { ++failures; }
    }
    p.type = 0x0E; p.sectors = 4152;
    p.start = 0xFFFFFFFFUL - (p.sectors - 1);
    if (rb_plan_primary_fat(&out, &p, entry, &disk, geometry, 1) || out.clusters != 4085
            || out.data != 0xFFFFFFFFUL - 4084) { ++failures; }
    ++p.start;
    if (rb_plan_primary_fat(&out, &p, entry, &disk, geometry, 1) != RB_FORMAT_RANGE) { ++failures; }
    p.start = 1; disk.capacity_high = 0; disk.capacity_low = p.sectors;
    if (rb_plan_primary_fat(&out, &p, entry, &disk, geometry, 1) != RB_FORMAT_RANGE) { ++failures; }
    ++disk.capacity_low; disk.mode = 0;
    if (rb_plan_primary_fat(&out, &p, entry, &disk, geometry, 1) != RB_FORMAT_EDD) { ++failures; }
    p.logical = 1;
    if (rb_plan_primary_fat(&out, &p, entry, &disk, geometry, 1) != RB_FORMAT_TARGET) { ++failures; }
    return failures;
}
