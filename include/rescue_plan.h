#ifndef RB_RESCUE_PLAN_H
#define RB_RESCUE_PLAN_H

#include "backup_plan.h"

/* Fresh BIOS discovery before and after a successful preliminary capture plan.
   Returns the probe status separately from the planner diagnostics. Any failed
   probe or changed device clears the plan payload. No file access or writes. */
rb_u16 rb_rescue_capture_plan(rb_backup_plan *result);

#endif
