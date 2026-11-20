; Read-only PIO on the legacy primary ATA master, under exclusive controller use.
; Both the identification and the MBR come through the same selected device.
bits 16
cpu 386
segment _TEXT public align=16 class=CODE use16
global _rb_ata_identify_words, _rb_ata_sector_zero
_rb_ata_identify_words:
    mov al, 0xec                ; IDENTIFY DEVICE
    jmp short transfer
_rb_ata_sector_zero:
    mov al, 0x20                ; READ SECTORS, LBA 0, one sector
transfer:
    push bp
    mov bp, sp
    pushf
    push es
    push fs
    pushad
    mov bl, al
    push ds
    pop es
    mov di, [bp+4]
    cli
    in al, 0xa1                 ; preserve the existing slave PIC mask
    mov bh, al
    or al, 0x40                 ; poll IDE IRQ14, leave the BIOS timer enabled
    out 0xa1, al
    mov ax, 0x40
    mov fs, ax
    mov si, [fs:0x6c]           ; start of one bounded ATA command
    mov ecx, 0x01000000         ; fallback if firmware stops advancing ticks
    sti
    mov dx, 0x3f6               ; alternate status, no interrupt acknowledgement
.channel:
    in al, dx
    cmp al, 0xff
    je .fail
    test al, 0x88               ; outstanding command on the channel
    jz .select
    call .within_deadline
    jb .channel
    jmp .fail
.select:
    mov dx, 0x1f6
    mov al, 0xe0                ; LBA, primary master, high LBA nibble zero
    out dx, al
    call .settle
.ready:
    in al, dx
    test al, al
    jz .fail
    cmp al, 0xff
    je .fail
    and al, 0xc8                ; BSY=0, DRDY=1, DRQ=0
    cmp al, 0x40
    je .issue
    call .within_deadline
    jb .ready
    jmp .fail
.issue:
    mov dx, 0x1f2
    mov al, 1
    out dx, al
    inc dx
    xor al, al
    out dx, al                  ; LBA low, mid and high
    inc dx
    out dx, al
    inc dx
    out dx, al
    mov dx, 0x1f7
    mov al, bl
    out dx, al
    call .settle
.data_wait:
    in al, dx
    test al, 0x80
    jnz .again
    test al, 0x21               ; ERR or device fault
    jnz .fail
    test al, 8
    jnz .data
.again:
    call .within_deadline
    jb .data_wait
    jmp .fail
.data:
    mov dx, 0x1f0
    push ecx
    mov cx, 256
    cld
    rep insw
    pop ecx
    call .settle
.complete:
    in al, dx
    test al, 0x80
    jnz .more
    test al, 0x21               ; ERR or device fault
    jnz .fail
    test al, 8                  ; allow final DRQ to deassert
    jnz .more
    test al, 0x40
    jnz .ok
.more:
    call .within_deadline
    jb .complete
.fail:
    mov ax, 1
    jmp short .return
.ok:
    mov dx, 0x1f7
    in al, dx                   ; acknowledge completion before BIOS floppy I/O
    and al, 0xe9
    cmp al, 0x40
    jne .fail
    xor ax, ax
.return:
    mov [bp-10], ax             ; saved low word of EAX
    cli
    mov al, bh
    out 0xa1, al
    popad
    pop fs
    pop es
    popf
    pop bp
    ret
.within_deadline:
    dec ecx
    jz .expired
    mov ax, [fs:0x6c]
    sub ax, si
    cmp ax, 91                  ; about five seconds; CF set while time remains
    ret
.expired:
    clc
    ret
.settle:
    mov dx, 0x3f6
    in al, dx
    in al, dx
    in al, dx
    in al, dx
    ret
