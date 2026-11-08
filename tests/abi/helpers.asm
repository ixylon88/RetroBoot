bits 16
cpu 386
%include "include/memory.inc"
segment _TEXT public align=16 class=CODE use16
global _rb_putc, _rb_check_context, _rb_far_read, _rb_asm_mix

_rb_putc:
    push bp
    mov bp, sp
    push ds
    push es
    pushad                         ; isolate the C caller from BIOS clobbers
    mov ax, [ss:bp + 4]
    out 0xE9, al                   ; same text to the headless test log
    mov ah, 0x0E
    mov bx, 0x0007
    pushf
    int 0x10
    popf
    popad
    pop es
    pop ds
    pop bp
    ret

_rb_check_context:
    push bp
    mov bp, sp
    pushf
    pop ax
    and ax, 0x0600                 ; DF clear and IF set
    cmp ax, 0x0200
    jne .bad
    mov ax, cs
    cmp ax, RB_LOAD_SEG
    jne .bad
    mov dx, ds
    cmp ax, dx
    jne .bad
    mov dx, ss
    cmp ax, dx
    jne .bad
    cmp sp, RB_STACK_LOW + 2
    jb .bad
    mov bx, [ss:bp + 4]            ; near pointer to a C stack local
    cmp word [bx], RB_STACK_GUARD
    jne .bad
    xor ax, ax
    pop bp
    ret
.bad:
    mov ax, 1
    pop bp
    ret

_rb_far_read:
    push bp
    mov bp, sp
    push es
    les bx, [ss:bp + 4]            ; explicit 16:16 pointer supplied by C
    mov ax, [es:bx]
    pop es
    pop bp
    ret

_rb_asm_mix:
    push bp
    mov bp, sp
    mov eax, [ss:bp + 4]
    movzx ecx, word [ss:bp + 8]
    add eax, ecx
    mov edx, eax
    shr edx, 16
    pop bp
    ret
