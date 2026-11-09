bits 16
cpu 386
org 0x7C00
%include "include/boot.inc"
    jmp short entry
    nop
    db 'RETROBT '
    dw 512                    ; BPB 11: bytes/sector
    db 4                      ; 13: sectors/cluster
    dw 1                      ; 14: reserved sectors (only this VBR)
    db 2                      ; 16: FAT copies
    dw 512                    ; 17: root entries
    dw 0                      ; 19: total sectors16
    db 0xF8
    dw 126                    ; 22: sectors/FAT
    dw 63, 255
    dd 0                      ; 28: hidden sectors = absolute volume start
    dd 128457                 ; 32: volume sectors
    db 0x80, 0, 0x29
    dd 0x52425431
    db 'RETROBOOT  '
    db 'FAT16   '
    db 'RBV1'                 ; 62: loader format
bootstrap_lba: dd 0            ; 66: first contiguous RBBOOT.SYS sector
bootstrap_sectors: dw 0        ; 70: includes checksum/padding, maximum 16
checksum: dw 0                ; 72: sum of all 256 VBR words must be zero
entry:
    cli
    xor ax, ax
    mov ss, ax
    mov sp, RB_VBR
    mov ds, ax
    mov es, ax
    cld
    sti
    cmp word [RB_CONTEXT], 0x5242
    jne failed
    mov cx, [bootstrap_sectors]
    jcxz failed
    cmp cx, RB_BOOT_LIMIT
    ja failed
    mov eax, [bootstrap_lba]
    mov edx, [RB_VBR + 28]
    cmp eax, edx
    jbe failed
    add edx, [RB_VBR + 32]
    jc failed
    movzx edi, cx
    add edi, eax
    jc failed
    cmp edi, edx
    ja failed
    mov bx, RB_BOOT
.read:
    call read_sector
    jc failed
    inc eax
    add bx, 512
    loop .read
    cmp dword [RB_BOOT + 2], 'RBB1'
    jne failed
    mov ax, [bootstrap_sectors]
    shl ax, 9
    cmp ax, [RB_BOOT + 6]
    jne failed
    mov cx, ax
    shr cx, 1
    xor dx, dx
    mov si, RB_BOOT
.sum:
    lodsw
    add dx, ax
    loop .sum
    test dx, dx
    jnz failed
    mov dl, [RB_DRIVE]
    jmp 0:RB_BOOT + RB_HEADER
failed:
    mov si, message
    jmp fatal

%include "boot/disk.inc"
%include "boot/fatal.inc"
message: db 'RB VBR ERROR', 13, 10, 0
    times 510 - ($ - $$) db 0
    dw 0xAA55
