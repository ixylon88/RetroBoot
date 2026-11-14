; Fixed 1440 KiB A: reader. Independent of all HDD discovery/context fields.
bits 16
cpu 386
%include "include/boot.inc"
segment _TEXT public align=16 class=CODE use16
global _rb_floppy_read
_rb_floppy_read:
    push bp
    mov bp, sp
    pushf
    push ds
    push es
    pushad
    mov eax, [ss:bp + 4]
    cmp eax, 2880
    jae .bad
    cmp word [ss:bp + 8], 0xFE00
    ja .bad
    mov bx, [ss:bp + 10]
    cmp word [bx], 0
    jne .bad
    mov si, ax
    mov di, 3
.retry:
    mov ax, si
    xor dx, dx
    mov cx, 18
    div cx
    mov cl, dl
    inc cl
    xor dx, dx
    mov bx, 2
    div bx
    mov ch, al
    mov dh, dl
    xor dl, dl
    xor ax, ax
    mov es, ax
    mov bx, RB_BUFFER
    mov ax, 0x0201
    pushad
    push ds
    push es
    stc
    int 0x13
    pop es
    pop ds
    popad
    jnc .copy
    pushad
    push ds
    push es
    xor ax, ax
    xor dl, dl
    int 0x13
    pop es
    pop ds
    popad
    dec di
    jnz .retry
.bad:
    mov ax, 1
    jmp .done
.copy:
    push ds
    pop es
    xor ax, ax
    mov ds, ax
    mov si, RB_BUFFER
    mov di, [ss:bp + 8]
    mov cx, 256
    cld
    rep movsw
    xor ax, ax
.done:
    mov [ss:bp - 10], ax
    popad
    pop es
    pop ds
    popf
    pop bp
    ret
