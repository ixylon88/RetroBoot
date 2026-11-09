; First HDD payload: loaded and CRC-checked by the FAT16 bootstrap.
; This assembly smoke test deliberately spans three 2 KiB clusters.
bits 16
cpu 386
org 0
%include "include/boot.inc"
    jmp short entry
    db 'RBS1'
    dw RB_HEADER
    dd 5000                    ; exact file bytes, checked against directory
    dd 0                       ; CRC32 over bytes 32..EOF, patched by builder
    dw RB_STAGE2_SEG, RB_HEADER
    dw 1                       ; format version
    times RB_HEADER - ($ - $$) db 0
entry:
    cli
    mov ax, cs
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, RB_STACK_TOP
    cld
    sti
    cmp dl, 0x80
    jne failed
    mov si, message
.print:
    lodsb
    test al, al
    jz .success
    out 0xE9, al
    pushad
    push ds
    push es
    mov ah, 0x0E
    mov bx, 7
    int 0x10
    pop es
    pop ds
    popad
    jmp .print
.success:
%ifdef RB_TEST
    mov ax, 0x10
    mov dx, 0xF4
    out dx, ax
%endif
    cli
.halt:
    hlt
    jmp .halt
failed:
    mov si, bad_drive
    jmp fatal
%include "boot/fatal.inc"
message: db 'RetroBoot Stage 2 ready', 13, 10, 'RB HDD PASS', 13, 10, 0
bad_drive: db 'RB STAGE2 DRIVE ERROR', 13, 10, 0
    times 5000 - ($ - $$) db 0xA5
