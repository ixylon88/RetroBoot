; Independent, read-only discovery; never consumes an HDD loader snapshot.
bits 16
cpu 386
%include "include/boot.inc"
segment _TEXT public align=16 class=CODE use16
global _rb_rescue_probe
_rb_rescue_probe:
    push bp
    mov bp, sp
    pushf
    push ds
    push es
    pushad
    push ds
    pop es
    mov di, [ss:bp + 4]
    mov cx, 8
    xor ax, ax
    cld
    rep stosw
    mov ds, ax
    mov es, ax
    mov di, RB_DRIVE
    mov cx, 48
    rep stosw
    cmp byte [0x0475], 0
    je .absent
    mov byte [RB_DRIVE], 0x80
    mov dl, 0x80
    mov bx, 0x55AA
    mov ah, 0x41
    push ds
    push es
    stc
    int 0x13
    pop es
    pop ds
    jc .chs
    cmp bx, 0xAA55
    jne .chs
    test cx, 1
    jz .chs
    mov si, RB_PARAMS
    mov word [si], 0x1E
    mov dl, 0x80
    mov ah, 0x48
    push ds
    push es
    stc
    int 0x13
    pop es
    pop ds
    jc .params
    cmp word [RB_PARAMS], 26
    jb .params
    cmp word [RB_PARAMS + 24], 512
    jne .params
    mov eax, [RB_CAPACITY]
    or eax, [RB_CAPACITY + 4]
    jz .params
    mov byte [RB_IO_MODE], 1
    jmp .ready
.chs:
    xor ax, ax
    mov es, ax
    xor di, di
    mov dl, 0x80
    mov ah, 8
    push ds
    push es
    stc
    int 0x13
    pop es
    pop ds
    jc .geometry
    test dl, dl
    jz .geometry
    mov al, cl
    and ax, 63
    jz .geometry
    mov [RB_SPT], ax
    mov al, dh
    xor ah, ah
    inc ax
    mov [RB_HEADS], ax
    mul word [RB_SPT]
    mov bx, ax
    mov al, ch
    mov ah, cl
    shr ah, 6
    inc ax
    mul bx
    mov [RB_CAPACITY], ax
    mov [RB_CAPACITY + 2], dx
.ready:
    mov word [RB_CONTEXT], 0x5242
    mov ax, [ss:bp - 4]         ; caller DS, saved before PUSHAD
    mov es, ax
    mov di, [ss:bp + 4]
    mov word [es:di], 0x80
    movzx ax, byte [RB_IO_MODE]
    mov [es:di + 2], ax
    mov ax, [RB_HEADS]
    mov [es:di + 4], ax
    mov ax, [RB_SPT]
    mov [es:di + 6], ax
    mov eax, [RB_CAPACITY]
    mov [es:di + 8], eax
    mov eax, [RB_CAPACITY + 4]
    mov [es:di + 12], eax
    xor ax, ax
    jmp .done
.absent:
    mov bx, 1
    jmp .clear
.params:
    mov bx, 2
    jmp .clear
.geometry:
    mov bx, 3
.clear:
    xor ax, ax
    mov es, ax
    mov di, RB_DRIVE
    mov cx, 48
    cld
    rep stosw
    mov ax, bx
.done:
    mov [ss:bp - 10], ax
    popad
    pop es
    pop ds
    popf
    pop bp
    ret
