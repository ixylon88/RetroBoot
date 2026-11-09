bits 16
cpu 386
org 0x0600
%include "include/boot.inc"

    ; No CS-relative data before the far jump: both BIOS entry forms work.
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
    mov di, RB_DRIVE
    mov cx, 48                  ; clear context/DAP/parameter buffer
    rep stosw                   ; AX=0, ES=0, DF=0 from relocation
    sti
    mov [RB_DRIVE], dl
    cmp dl, 0x80
    jne failed
    mov bx, 0x55AA
    mov ah, 0x41
    push ds
    int 0x13
    pop ds
    jc chs_init
    cmp bx, 0xAA55
    jne chs_init
    test cx, 1
    jz chs_init
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
    inc byte [RB_IO_MODE]
    jmp initialized
failed:
    mov si, message
    jmp fatal
chs_init:
    xor ax, ax
    mov es, ax
    xor di, di                 ; guard against legacy BIOS ES:DI quirks
    mov dl, [RB_DRIVE]
    mov ah, 8
    push ds
    int 0x13
    pop ds
    jc failed
    mov al, cl
    and ax, 63
    jz failed
    mov [RB_SPT], ax
    mov al, dh
    xor ah, ah
    inc ax
    mov [RB_HEADS], ax
    mul word [RB_SPT]
    mov bx, ax                 ; sectors/cylinder, <= 256 * 63
    mov al, ch
    mov ah, cl
    shr ah, 6
    inc ax                     ; cylinder count, 1..1024
    mul bx
    mov [RB_CAPACITY], ax
    mov [RB_CAPACITY + 2], dx
initialized:
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
%define RB_FIXED_VBR_BUFFER 1  ; sole call above uses BX=7C00h, within bound
%include "boot/disk.inc"
%include "boot/fatal.inc"
message: db 'RB MBR ERROR', 13, 10, 0
    ; Fixed parameter slot; bytes 440..511 are owned by the disk layout.
    times 432 - ($ - $$) db 0
    db 'RBM1'
vbr_lba: dd 0
    times 440 - ($ - $$) db 0
