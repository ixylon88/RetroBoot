#ifndef RB_RESCUE_PLAN_H
#define RB_RESCUE_PLAN_H

#include "backup_payload.h"

/* Fresh BIOS discovery before and after two validated live payload passes.
   Returns the probe status separately from the planner diagnostics. Any failed
   probe or changed device clears all plan claims and CRCs. No file or writes. */
rb_u16 rb_rescue_capture_payloads(rb_backup_payloads *result);

#endif
