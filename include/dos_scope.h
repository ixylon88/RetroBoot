#ifndef RB_DOS_SCOPE_H
#define RB_DOS_SCOPE_H

#include "state.h"

#define RB_DOS_PROFILES 3U
/* Physical slots of all supported, approved DOS profiles, or zero. */
rb_u16 rb_config_dos_slots(const rb_config_result *config);
/* Scope for an independently reacquired, linked configuration and installation state. */
rb_u16 rb_dos_recovery_slots(const rb_config_result *config, const rb_install_state *state);
/* Zero-based active approved slot in an isolated MBR view, or 4. */
rb_u16 rb_dos_view_slot(const rb_u8 *mbr, rb_u16 slots);

#endif
