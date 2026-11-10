; C/16 adapter for the same bounded, read-only EDD/CHS path as the loader.
bits 16
cpu 386
%include "include/boot.inc"
segment _TEXT public align=16 class=CODE use16
global _rb_disk_read

_rb_disk_read:
    push bp
    mov bp, sp
    pushf
    push ds
    push es
    pushad
    mov bx, [ss:bp + 8]        ; near destination; DS=SS for our C runtime
    push ds
    pop es
    xor ax, ax
    mov ds, ax
    cmp word [RB_CONTEXT], 0x5242
    jne .bad
    cmp byte [RB_DRIVE], 0x80
    jne .bad
    cmp byte [RB_IO_MODE], 1
    ja .bad
    je .ready
    cmp dword [RB_HEADS], 1
    jb .bad
    cmp dword [RB_HEADS], 256
    ja .bad
    cmp dword [RB_SPT], 1
    jb .bad
    cmp dword [RB_SPT], 63
    ja .bad
.ready:
    mov eax, [ss:bp + 4]
    call read_sector
    jc .bad
    xor ax, ax
    jmp .done
.bad:
    mov ax, 1
.done:
    mov [ss:bp - 10], ax       ; returned low word of saved EAX
    popad
    pop es
    pop ds
    popf
    pop bp
    ret

%include "boot/disk.inc"
