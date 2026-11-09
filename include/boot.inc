; HDD loader contract, version 1. Physical addresses unless stated otherwise.
%define RB_DRIVE       0x0500
%define RB_CONTEXT     0x0502
%define RB_DAP         0x0520
%define RB_PARAMS      0x0540
%define RB_CAPACITY    (RB_PARAMS + 16) ; uint64, sector count from AH=48h
%define RB_MBR         0x0600
%define RB_BUFFER      0x1000
%define RB_BOOT        0x2000
%define RB_BOOT_LIMIT  16             ; sectors, <= 8 KiB
%define RB_VBR         0x7C00
%define RB_STAGE2_SEG  0x1000
%define RB_STAGE2_MAX  0xC000         ; 48 KiB including header
%define RB_HEADER     32
%define RB_STACK_TOP  0xFFFE
