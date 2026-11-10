; Shared C runtime memory contract. Physical segment 10000h..1FFFFh.
%define RB_LOAD_SEG       0x1000
%define RB_SEGMENT_BYTES  0x10000
%define RB_HDD_FILE_MAX   0xC000
%define RB_STACK_LOW      0xE000
%define RB_STACK_TOP      0xFFFE
%define RB_HEADER_BYTES   32
%define RB_STACK_GUARD    0xA55A

%if RB_STACK_LOW >= RB_STACK_TOP || RB_STACK_TOP >= RB_SEGMENT_BYTES
    %error Invalid runtime stack range
%endif
