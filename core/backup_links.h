#ifndef RB_BACKUP_LINKS_H
#define RB_BACKUP_LINKS_H

#include "state.h"

/* Internal shared rule for already validated, identity-bound selected records.
   Returns the first incompatible profile index, or RB_CONFIG_NONE. No I/O,
   readiness proof, update-history check or authority to start/restore an OS. */
rb_u16 rb_backup_unlinked_profile(const rb_config *config, const rb_install_state *state);

#endif
