bits 16
cpu 386
%include "include/boot.inc"
segment _TEXT public align=16 class=CODE use16
global _rb_dos_geometry

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

%ifndef RB_GEOMETRY_ONLY
global _rb_video_console, _rb_dos_write_record, _rb_dos_write_mbr

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

; The record entry point continues to reject sector zero. The MBR entry
; point takes no address and preserves the complete loader/disk identity.
%macro write_frame 0
    push bp
    mov bp, sp
    pushf
    push ds
    push es
    pushad
    push ds
    pop es
    xor ax, ax
    mov ds, ax
%endmacro

_rb_dos_write_mbr:
    write_frame
    mov bx, [ss:bp + 4]
    cmp bx, 0xfe00
    ja dos_write_bad
    mov di, bx
    mov si, RB_MBR
    mov cx, 223
    cld
    repe cmpsw
    jne dos_write_bad
    cmp word [es:bx + 510], 0xaa55
    jne dos_write_bad
    xor eax, eax
    jmp short dos_write

_rb_dos_write_record:
    write_frame
    mov bx, [ss:bp + 8]
    mov eax, [ss:bp + 4]
    cmp eax, [RB_MBR + 436]
    jbe dos_write_bad
dos_write:
    cmp word [RB_CONTEXT], 0x5242
    jne dos_write_bad
    cmp word [RB_DRIVE], 0x0180
    jne dos_write_bad
    cmp bx, 0xfe00
    ja dos_write_bad
    cmp dword [RB_MBR + 432], 'RBM1'
    jne dos_write_bad
    cmp dword [RB_CAPACITY + 4], 0
    jne .address
    cmp eax, [RB_CAPACITY]
    jae dos_write_bad
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
    jc dos_write_bad
    xor ax, ax
    jmp short dos_write_done
dos_write_bad:
    mov ax, 1
dos_write_done:
    mov [ss:bp - 10], ax
    popad
    pop es
    pop ds
    popf
    pop bp
    ret
%endif
