bits 16
cpu 386
segment _TEXT public align=16 class=CODE use16
global _rb_dos_geometry, _rb_video_console

; Return cylinders, heads and sectors/track as reported for BIOS disk 80h.
_rb_dos_geometry:
    push bp
    mov bp, sp
    pushf
    push es
    pushad
    xor ax, ax
    mov es, ax
    xor di, di
    mov dl, 0x80
    mov ah, 8
    push ds
    push bp
    int 0x13
    pop bp
    pop ds
    mov si, [ss:bp + 4]
    jc .failed
    movzx ax, ch
    mov bx, cx
    and bx, 0xc0
    shl bx, 2
    or ax, bx
    inc ax
    mov [si], ax
    movzx ax, dh
    inc ax
    mov [si+2], ax
    and cx, 63
    mov [si+4], cx
    jmp short .done
.failed:
    mov word [si], 0
    mov dword [si+2], 0
.done:
    popad
    pop es
    popf
    pop bp
    ret

; Restore the visible BIOS text cursor and clear the menu before DOS takes over.
_rb_video_console:
    pushf
    push ds
    push es
    pushad
    mov ax, 3
    int 0x10
    popad
    pop es
    pop ds
    popf
    ret
