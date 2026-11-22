; Owned 1,440 KiB FAT12 rescue medium. RBRESCUE.BIN is contiguous at cluster 2.
; Fixed layout/length/whole-file CRC are bound by the builder, not a FAT reader.
bits 16
cpu 386
org 0x7C00
%include "include/memory.inc"
%if RB_RESCUE_BYTES < 33 || RB_RESCUE_BYTES > RB_HDD_FILE_MAX
    %error Invalid rescue payload size
%endif
%define FIRST_END (33 + (RB_RESCUE_BYTES + 511) / 512)
%ifdef RB_BACKUP_BYTES
    %if RB_BACKUP_BYTES < 33 || RB_BACKUP_BYTES > RB_HDD_FILE_MAX
        %error Invalid backup payload size
    %endif
%endif
    jmp short normalize
    nop
%ifdef RB_BACKUP_BYTES
    db 'RBBKUP01'                ; one witness shared by both boot choices
%elifdef RB_ATA_RECOVERY_PROFILE
    db 'RBTARG03'                ; template capability in the FAT OEM field
%else
    db 'RETROBT '
%endif
    dw 512
    db 1
    dw 1
    db 2
    dw 224, 2880
    db 0xF0
    dw 9, 18, 2
    dd 0, 0
    db 0, 0, 0x29
    dd 0x52425231
    db 'RB RESCUE  ', 'FAT12   '
normalize:
    jmp 0:entry
entry:
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7C00
    cld
    sti
    mov [drive], dl
    cmp dl, 0                  ; defined boot medium A:, target remains 80h
    jne failed
    push ds
    int 0x12
    pop ds
    cmp ax, (RB_LOAD_SEG * 16 + RB_SEGMENT_BYTES) / 1024
    jb failed
    mov ax, [0x040E]
    test ax, ax
    jz .memory
    cmp ax, RB_LOAD_SEG + RB_SEGMENT_BYTES / 16
    jb failed
.memory:
%ifdef RB_BACKUP_BYTES
    mov si, menu
    call print_line
.choose:
    xor ah, ah
    push ds
    int 0x16
    pop ds
    mov bp, history_program
    cmp al, '1'
    je .selected
    mov bp, backup_program
    cmp al, '2'
    jne .choose
.selected:
    mov ax, [bp]
    mov [lba], ax
%endif
    mov ax, RB_LOAD_SEG
    mov es, ax
    xor di, di
    mov cx, RB_SEGMENT_BYTES / 2
    mov ax, 0xA5A5
    rep stosw
    xor bx, bx
.sector:
    mov byte [retries], 3
.retry:
    mov ax, [lba]
    xor dx, dx
    mov cx, 18
    div cx
    mov cl, dl
    inc cl
    xor dx, dx
    mov si, 2
    div si
    mov ch, al
    mov dh, dl
    mov dl, [drive]
    mov ax, 0x0201
    pushad
    push ds
    push es
    stc
    int 0x13
    pop es
    pop ds
    popad
    jnc .read
    pushad
    push ds
    push es
    xor ah, ah
    mov dl, [drive]
    int 0x13
    pop es
    pop ds
    popad
    dec byte [retries]
    jnz .retry
    jmp failed
.read:
    add bx, 512
    inc word [lba]
%ifdef RB_BACKUP_BYTES
    mov ax, [lba]
    cmp ax, [bp+2]
%else
    cmp word [lba], FIRST_END
%endif
    jb .sector
    cld
    xor si, si
%ifdef RB_BACKUP_BYTES
    mov cx, [bp+4]
%else
    mov cx, RB_RESCUE_BYTES
%endif
    mov edx, 0xFFFFFFFF
.byte:
    xor dl, [es:si]
    inc si
    mov al, 8
.bit:
    shr edx, 1
    jnc .next
    xor edx, 0xEDB88320
.next:
    dec al
    jnz .bit
    loop .byte
    not edx
%ifdef RB_BACKUP_BYTES
    cmp edx, [bp+6]
%else
    cmp edx, RB_RESCUE_CRC
%endif
    jne failed
    mov dl, [drive]
    jmp RB_LOAD_SEG:32
failed:
    cld
    mov si, message
%ifdef RB_BACKUP_BYTES
    call print_line
.halt:
    cli
    hlt
    jmp .halt
print_line:
%endif
.print:
    lodsb
    test al, al
    jz .halt
    out 0xE9, al
    mov ah, 0x0E
    mov bx, 7
    pushad
    push ds
    push es
    pushf
    int 0x10
    popf
    pop es
    pop ds
    popad
    jmp .print
.halt:
%ifdef RB_BACKUP_BYTES
    ret
    ; First LBA, exclusive end, exact length, whole-file CRC32.
history_program dw 33, FIRST_END, RB_RESCUE_BYTES
    dd RB_RESCUE_CRC
backup_program dw FIRST_END, FIRST_END + (RB_BACKUP_BYTES + 511) / 512, RB_BACKUP_BYTES
    dd RB_BACKUP_CRC
menu db RB_BACKUP_MENU, 13, 10, 0
%else
    cli
    hlt
    jmp .halt
%endif
drive db 0
retries db 0
lba dw 33
message db 'RB RESCUE LOAD ERROR', 13, 10, 0
times 510 - ($ - $$) db 0
dw 0xAA55
