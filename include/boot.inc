; HDD loader contract, version 1. Physical addresses unless stated otherwise.
%include "include/memory.inc"
%define RB_DRIVE       0x0500
%define RB_IO_MODE     0x0501         ; 0=CHS, 1=EDD, selected once by MBR
%define RB_CONTEXT     0x0502
%define RB_HEADS       0x0504         ; uint32, AH=08h heads + 1 (up to 256)
%define RB_SPT         0x0508         ; uint32, AH=08h sectors/track (1..63)
%define RB_DAP         0x0520
%define RB_PARAMS      0x0540
%define RB_CAPACITY    (RB_PARAMS + 16) ; uint64: EDD capacity / CHS reach
%define RB_MBR         0x0600
%define RB_BUFFER      0x1000
%define RB_BOOT        0x2000
%define RB_BOOT_LIMIT  16             ; sectors, <= 8 KiB
%define RB_VBR         0x7C00
%define RB_STAGE2_SEG  RB_LOAD_SEG
%define RB_STAGE2_MAX  RB_HDD_FILE_MAX ; 48 KiB including header
%define RB_HEADER     RB_HEADER_BYTES
