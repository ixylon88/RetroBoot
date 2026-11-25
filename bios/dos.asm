bits 16
cpu 386
%include "include/boot.inc"
segment _TEXT public align=16 class=CODE use16
global _rb_dos_geometry, _rb_video_console, _rb_dos_write_record

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

; One reviewed management file sector on the boot disk. Never retry a write
; with uncertain completion. The C caller reopens the disk for readback.
_rb_dos_write_record:
    push bp
    mov bp, sp
    pushf
    push ds
    push es
    pushad
    mov bx, [ss:bp + 8]
    push ds
    pop es
    xor ax, ax
    mov ds, ax
    cmp word [RB_CONTEXT], 0x5242
    jne .bad
    cmp word [RB_DRIVE], 0x0180      ; BIOS disk 0x80, EDD route
    jne .bad
    cmp bx, 0xfe00
    ja .bad
    cmp dword [RB_MBR + 432], 'RBM1'
    jne .bad
    mov eax, [ss:bp + 4]
    cmp eax, [RB_MBR + 436]         ; strictly beyond the management VBR
    jbe .bad
    cmp dword [RB_CAPACITY + 4], 0
    jne .address
    cmp eax, [RB_CAPACITY]
    jae .bad
.address:
    mov si, RB_DAP
    mov dword [si], 0x00010010
    mov [si + 4], bx
    mov [si + 6], es
    mov [si + 8], eax
    mov dword [si + 12], 0
    mov dl, 0x80
    mov ax, 0x4301                  ; EDD extended write with verification
    push bp
    stc
    int 0x13
    pop bp
    jc .bad
    xor ax, ax
    jmp short .done
.bad:
    mov ax, 1
.done:
    mov [ss:bp - 10], ax
    popad
    pop es
    pop ds
    popf
    pop bp
    ret
