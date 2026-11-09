bits 16
cpu 386
org 0x0600
%include "include/boot.inc"

    jmp 0:start + 0x7600          ; normalize BIOS 0000:7C00 / 07C0:0000
start:
    cli
    xor ax, ax
    mov ss, ax
    mov sp, 0x7C00
    mov ds, ax
    mov es, ax
    cld
    mov si, 0x7C00
    mov di, RB_MBR
    mov cx, 256
    rep movsw
    jmp 0:relocated
relocated:
    sti
    mov [RB_DRIVE], dl
    cmp dl, 0x80
    jne failed
    mov bx, 0x55AA
    mov ah, 0x41
    push ds
    int 0x13
    pop ds
    jc failed
    cmp bx, 0xAA55
    jne failed
    test cx, 1
    jz failed
    mov si, RB_PARAMS
    mov word [si], 0x1E
    mov dl, [RB_DRIVE]
    mov ah, 0x48
    push ds
    int 0x13
    pop ds
    jc failed
    cmp word [RB_PARAMS], 26
    jb failed
    cmp word [RB_PARAMS + 24], 512
    jne failed
    mov word [RB_CONTEXT], 0x5242
    xor ax, ax
    mov es, ax
    mov eax, [vbr_lba]
    mov bx, RB_VBR
    call read_sector
    jc failed
    cmp word [RB_VBR + 510], 0xAA55
    jne failed
    cmp dword [RB_VBR + 62], 'RBV1'
    jne failed
    mov si, RB_VBR
    mov cx, 256
    xor dx, dx
.sum:
    lodsw
    add dx, ax
    loop .sum
    test dx, dx
    jnz failed
    mov dl, [RB_DRIVE]
    jmp 0:RB_VBR
failed:
    mov si, message
    jmp fatal

%include "boot/edd.inc"
%include "boot/fatal.inc"
message: db 'RB MBR ERROR', 13, 10, 0
    ; Fixed parameter slot; bytes 440..511 are owned by the disk layout.
    times 432 - ($ - $$) db 0
    db 'RBM1'
vbr_lba: dd 0
    times 440 - ($ - $$) db 0
