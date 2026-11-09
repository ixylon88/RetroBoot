; Test fixture only: raw floppy, payload in sectors 2..18 of its first track.
; This is not the RetroBoot MBR, FAT VBR, installer or recovery floppy.
bits 16
cpu 386
org 0x7C00
%include "include/memory.inc"
%ifndef RB_PROBE_SECTORS
    %error The image builder must supply RB_PROBE_SECTORS
%endif
%if RB_PROBE_SECTORS < 1 || RB_PROBE_SECTORS > 17
    %error Probe must fit into the remaining first-track sectors
%endif

    jmp 0x0000:entry
entry:
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7C00
    cld
    sti
    mov [drive], dl
    int 0x12                       ; conventional memory, in KiB
    cmp ax, (RB_LOAD_SEG * 16 + RB_SEGMENT_BYTES) / 1024
    jb failed
    mov ax, [0x040E]               ; EBDA base, zero means not reported
    test ax, ax
    jz .memory_ok
    cmp ax, RB_LOAD_SEG + RB_SEGMENT_BYTES / 16
    jb failed
.memory_ok:
    mov ax, 3
    push ds
    int 0x10
    pop ds
    cld
    mov ax, RB_LOAD_SEG
    mov es, ax
    xor di, di
    mov cx, RB_SEGMENT_BYTES / 2
    mov ax, 0xA5A5                 ; poison RAM so a missing BSS clear fails
    rep stosw
    xor bx, bx
.sector:
    mov byte [retries], 3
.retry:
    mov ax, 0x0201
    xor cx, cx
    mov cl, [sector]
    xor dh, dh
    mov dl, [drive]
    pushad
    push ds
    push es
    int 0x13
    pop es
    pop ds
    popad
    jnc .read
    xor ax, ax
    mov dl, [drive]
    pushad
    push ds
    push es
    int 0x13                       ; bounded reset/retry on read failure
    pop es
    pop ds
    popad
    dec byte [retries]
    jnz .retry
    jmp failed
.read:
    add bx, 512
    inc byte [sector]
    cmp byte [sector], 2 + RB_PROBE_SECTORS
    jb .sector
    mov dl, [drive]
    jmp RB_LOAD_SEG:0

failed:
    mov si, error_message
.print:
    lodsb
    test al, al
    jz .exit
    out 0xE9, al
    mov ah, 0x0E
    mov bx, 0x0007
    pushad
    push ds
    push es
    pushf
    int 0x10
    popf
    pop es
    pop ds
    popad
    jmp .print
.exit:
    mov ax, 0x12
    mov dx, 0xF4
    out dx, ax
    cli
.halt:
    hlt
    jmp .halt

drive db 0
sector db 2
retries db 3
error_message db 'RB PROBE BOOT FAIL', 13, 10, 0
times 510-($-$$) db 0
dw 0xAA55
