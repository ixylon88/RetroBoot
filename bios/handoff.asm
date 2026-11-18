; Real-mode transfer shared by checked DOS boots and the T07 fixture.
bits 16
cpu 386
%include "include/boot.inc"
%include "include/handoff.inc"
%ifndef RB_HANDOFF_FAULT
%define RB_HANDOFF_FAULT 0
%endif
segment _TEXT public align=16 class=CODE use16
global _rb_handoff

_rb_handoff:
    push bp
    mov bp, sp
    pushf
    pop bx                     ; restore the caller's IF, explicitly clear DF
    cli
    mov si, [ss:bp + 4]         ; prepared sector followed by the raw MBR entry
    xor ax, ax
    mov es, ax
    mov di, RB_VBR
    mov cx, 256
    cld
    rep movsw
    mov di, RB_HANDOFF_ENTRY
    mov cx, 8
    rep movsw
%if RB_HANDOFF_FAULT = 9
    xor byte [es:RB_HANDOFF_ENTRY + 1], 1
%endif
    mov ds, ax
    mov es, ax
    mov fs, ax
    mov gs, ax
    mov ss, ax
    mov sp, RB_HANDOFF_STACK
%if RB_HANDOFF_FAULT = 3
    ; Keep the deliberately wrong stack outside the entire Stage 2 segment.
    ; Its IRET frame must not corrupt loaded code as that code grows.
    mov ax, 0x2000
    mov ss, ax
    xor ax, ax
%elif RB_HANDOFF_FAULT = 4
    mov sp, 0x7B00
%endif
    and bx, 0x0200
    or bx, 2
%if RB_HANDOFF_FAULT = 7
    or bx, 0x0400
%elif RB_HANDOFF_FAULT = 8
    and bx, 0xFDFF
%endif
    push bx                    ; IRET restores flags and leaves the stack at 7C00
    push word 0
    push word RB_VBR
    mov bx, ax
    mov cx, ax
    mov di, ax
    mov bp, ax
    mov dx, 0x0080
    mov si, RB_HANDOFF_ENTRY
%if RB_HANDOFF_FAULT = 1
    mov ds, dx
%elif RB_HANDOFF_FAULT = 2
    mov es, dx
%elif RB_HANDOFF_FAULT = 5
    inc si
%elif RB_HANDOFF_FAULT = 6
    inc dx
%endif
    iret
