#ifndef RB_INSTALL_LAYOUT_H
#define RB_INSTALL_LAYOUT_H
#include "fat_plan.h"

#define RB_INSTALL_TABLES 4
#define RB_INSTALL_NO_LBA 0xffffffffUL
typedef rb_u8 rb_install_tables[RB_INSTALL_TABLES][512];
typedef struct {
    rb_rescue_device disk;
    rb_u16 geometry[3], bits;
    rb_u32 start, end, error_lba;
    rb_install_tables tables;
} rb_install_snapshot;

/* One BIOS drive and one reviewed profile, refreshed on each observation. */
const char *rb_install_observe(rb_install_snapshot *s, rb_u16 os, rb_u16 slot);
const char *rb_install_empty_boot(rb_install_snapshot *s, rb_sector_reader read);
rb_u32 rb_install_table_lba(rb_u16 table);
void rb_install_render(rb_install_tables out, const rb_install_tables in, rb_u16 slot);
void rb_install_changes(const rb_install_tables from, const rb_install_tables to);
void rb_install_target(const rb_install_snapshot *s);
void rb_install_error(const char *message, rb_u32 lba);
extern const rb_u32 rb_install_capacity;
extern const char *const rb_install_systems[3];
#endif
