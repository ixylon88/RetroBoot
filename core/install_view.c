/* Apply or undo the reviewed Windows 95 OSR2/P2 view on the enrolled disk pair. */
#include "install_layout.h"
#include "ide_pair.h"
#include "mbr_compare.h"
#include "mbr_console.h"
#include "rescue_text.h"
#include "install_approval.h"

#define STEPS (sizeof(write_order) / sizeof(write_order[0]))
enum { WIN95_OSR2 = 1, TARGET_SLOT = 2 };
rb_u16 __cdecl rb_ata_install_write(rb_u16 step, const rb_u8 *sector);

static rb_install_snapshot disk;
static rb_install_tables original, planned;
static rb_u8 physical[512];

static rb_u16 __cdecl read_primary(rb_u32 lba, rb_u8 *out, void *opaque)
{
    (void)opaque;
    return rb_ata_copy_read(0, lba, out);
}

static const char *target_clear(void)
{
    const char *error = rb_install_empty_boot(&disk, rb_disk_read);
    return error ? error : rb_install_empty_boot(&disk, read_primary);
}

static const char *inspect(rb_u16 *done)
{
    rb_u16 t, step;
    const char *error = rb_install_observe(&disk, WIN95_OSR2, TARGET_SLOT);
    if (error) { return error; }
    /* The ATA identities carry the full sector count even with cylinder-rounded BIOS CHS. */
    error = rb_ide_check_pair(rb_install_capacity, 0);
    if (error) { return error; }
    if (!rb_ide_can_flush()) { return RB_RS_FW_FLUSH; }
    for (t = 0; t < RB_INSTALL_TABLES; ++t) {
        disk.error_lba = rb_install_table_lba(t);
        if (rb_ata_copy_read(1, disk.error_lba, original[t])
                || rb_ata_copy_read(0, disk.error_lba, physical)) { return RB_RS_FR_IO; }
        if (!equal(original[t], approved[t], 512)) { return RB_RS_IV_BACKUP; }
        if (!equal(physical, disk.tables[t], 512)) { return RB_RS_IP_CHANGED; }
    }
    rb_install_render(planned, original, TARGET_SLOT);
    for (t = 0; t < RB_INSTALL_TABLES; ++t) {
        disk.error_lba = rb_install_table_lba(t);
        if (!equal(disk.tables[t], original[t], 512) && !equal(disk.tables[t], planned[t], 512)) {
            return RB_RS_IV_FOREIGN;
        }
    }
    /* Every completed write is one more leading sector in the prescribed order.
       Undoing that prefix in reverse makes a second interruption recoverable. */
    *done = 0;
    for (step = 0; step < STEPS; ++step) {
        t = write_order[step];
        if (equal(disk.tables[t], planned[t], 512)) {
            if (*done != step) {
                disk.error_lba = rb_install_table_lba(t);
                return RB_RS_IV_FOREIGN;
            }
            ++*done;
        }
    }
    disk.error_lba = RB_INSTALL_NO_LBA;
    return rb_ide_check_pair(rb_install_capacity, 0);
}

static rb_u16 blocked(const char *error)
{
    rb_install_error(error, disk.error_lba);
    return 1;
}

static rb_u16 cancel(void)
{
    line(RB_RS_FW_CANCEL);
    return 0;
}

rb_u16 __cdecl rb_install_view_run(rb_u16 drive)
{
    rb_rescue_device device;
    rb_u16 geometry[3], done, actual, step, t, i;
    int restore;
    const char *error;
    const rb_u8 *data;

    disk.error_lba = RB_INSTALL_NO_LBA;
    line(RB_RS_IV_TITLE);
    print(rb_install_systems[WIN95_OSR2]); line("  P2");
    if (rb_ide_load_pair(drive) != 1) { return blocked(RB_RS_FR_PROFILE); }
    error = inspect(&done);
    if (error) { return blocked(error); }
    restore = done != 0;
    if (!restore && (error = target_clear()) != 0) { return blocked(error); }
    device = disk.disk;
    for (i = 0; i < 3; ++i) { geometry[i] = disk.geometry[i]; }
    rb_ide_print_pair();
    rb_install_target(&disk);
    count(RB_RS_FW_COUNT " ", done);
    if (done == STEPS) { line("RB INSTALL VIEW ACTIVE"); }
    else { line(restore ? RB_RS_IV_PARTIAL : RB_RS_IV_ORIGINAL); }
    rb_install_changes(disk.tables, restore ? original : planned);
    line(restore ? RB_RS_IV_RESTORE : RB_RS_IV_APPLY);
    if (rb_console_key() != (restore ? 'R' : 'A')) { return cancel(); }
    line(RB_RS_FW_CONFIRM);
    if (rb_console_key() != '0' + TARGET_SLOT) { return cancel(); }

    for (;;) {
        error = inspect(&actual);
        if (error) { return blocked(error); }
        if (actual != done || !equal((const rb_u8 *)&device, (const rb_u8 *)&disk.disk, sizeof(device))
                || !equal((const rb_u8 *)geometry, (const rb_u8 *)disk.geometry, sizeof(geometry))) {
            return blocked(RB_RS_IP_CHANGED);
        }
        if (!restore && (error = target_clear()) != 0) { return blocked(error); }
        if (done == (restore ? 0 : STEPS)) { break; }
        step = restore ? done - 1 : done;
        t = write_order[step];
        data = restore ? original[t] : planned[t];
        disk.error_lba = rb_install_table_lba(t);
        if (rb_ata_install_write(step, data) || rb_ata_copy_read(0, disk.error_lba, physical)
                || !equal(physical, data, 512)) { return blocked(RB_RS_IV_IO); }
        done = restore ? done - 1 : done + 1;
    }
    line(restore ? "RB INSTALL VIEW RESTORE PASS" : "RB INSTALL VIEW APPLY PASS");
    return 0;
}
