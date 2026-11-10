; Real-mode handoff: independent low-memory entry copy and stack below VBR.
%define RB_HANDOFF_ENTRY 0x0800       ; 16 bytes, outside relocated MBR and IVT/BDA
%define RB_HANDOFF_STACK 0x7C00
%define RB_HANDOFF_RECEIPT 0x0820     ; 32 bytes, test VBR evidence only
