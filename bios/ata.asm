; Exclusive, polled PIO on the two legacy IDE masters. The primary master
; exposes only IDENTIFY and a read of LBA 0. Only the secondary entry point
; can write, and only its six pre-enrolled recovery records.
bits 16
cpu 386
segment _TEXT public align=16 class=CODE use16
global _rb_ata_identify_words, _rb_ata_read_sector, _rb_ata_write_recovery

_rb_ata_identify_words:         ; channel, buffer
    mov al, 0xec
    jmp short transfer
_rb_ata_read_sector:            ; channel, LBA, buffer
    mov al, 0x20
    jmp short transfer
_rb_ata_write_recovery:         ; LBA, buffer (no caller-supplied channel)
    mov al, 0x30
transfer:
    push bp
    mov bp, sp
    pushf
    push es
    push fs
    pushad
    sub sp, 6
%define TASK_PORT word [ss:bp-40]
%define ALT_PORT  word [ss:bp-42]
%define IO_LBA    byte [ss:bp-44]
    mov bl, al
    xor cx, cx
    mov ax, [bp+4]
    mov di, [bp+6]
    cmp bl, 0x30
    jne .input
    mov cx, ax
    test cx, cx                 ; preserve the recovery disk's label at LBA 0
    jz .invalid
    mov ax, 1                   ; fixed secondary master
    jmp short .bounds
.input:
    cmp ax, 1
    ja .invalid
    cmp bl, 0xec
    je .bounds
    mov cx, [bp+6]
    mov di, [bp+8]
    test ax, ax
    jnz .bounds
    test cx, cx                 ; source disk reads stop at its MBR
    jnz .invalid
.bounds:
    cmp cx, 6
    ja .invalid
    cmp di, 0xfe00
    ja .invalid
    mov IO_LBA, cl
    mov dx, 0x1f0
    mov cl, 0x40                ; slave PIC IRQ14
    test ax, ax
    jz .ports
    mov dx, 0x170
    mov cl, 0x80                ; slave PIC IRQ15
.ports:
    mov TASK_PORT, dx
    add dx, 0x206
    mov ALT_PORT, dx
    push ds
    pop es
    cli
    in al, 0xa1
    mov bh, al
    or al, cl
    out 0xa1, al
    mov ax, 0x40
    mov fs, ax
    call .deadline
    sti
.channel:
    in al, dx
    cmp al, 0xff
    je .fail
    test al, 0x88
    jz .select
    call .within_deadline
    jb .channel
    jmp .fail
.select:
    mov dx, TASK_PORT
    add dx, 6
    mov al, 0xe0                ; LBA, master, high nibble zero
    out dx, al
    call .settle
.ready:
    in al, dx
    test al, al
    jz .fail
    cmp al, 0xff
    je .fail
    and al, 0xc8
    cmp al, 0x40
    je .issue
    call .within_deadline
    jb .ready
    jmp .fail
.issue:
    mov dx, TASK_PORT
    add dx, 2
    mov al, 1
    out dx, al
    inc dx
    mov al, IO_LBA
    out dx, al
    inc dx
    xor al, al
    out dx, al
    inc dx
    out dx, al
    add dx, 2
    mov al, bl
    out dx, al
    call .settle
.data_wait:
    in al, dx
    test al, 0x80
    jnz .again
    test al, 0x21
    jnz .fail
    test al, 8
    jnz .data
.again:
    call .within_deadline
    jb .data_wait
    jmp .fail
.data:
    mov dx, TASK_PORT
    push ecx
    mov cx, 256
    cld
    cmp bl, 0x30
    jne .read
    push si
    mov si, di
    rep outsw
    pop si
    jmp short .transferred
.read:
    rep insw
.transferred:
    pop ecx
    call .settle
.complete:
    in al, dx
    test al, 0x80
    jnz .more
    test al, 0x21
    jnz .fail
    test al, 8
    jnz .more
    test al, 0x40
    jnz .ack
.more:
    call .within_deadline
    jb .complete
.fail:
    mov ax, 1
    jmp short .return
.ack:
    mov dx, TASK_PORT
    add dx, 7
    in al, dx                   ; acknowledge before BIOS floppy I/O
    and al, 0xe9
    cmp al, 0x40
    jne .fail
    cmp bl, 0x30
    jne .ok
    mov bl, 0xe7                ; FLUSH CACHE on the same secondary master
    mov al, bl
    out dx, al
    call .deadline
    call .settle
    jmp short .complete
.ok:
    xor ax, ax
.return:
    mov [bp-10], ax
    cli
    mov al, bh
    out 0xa1, al
    jmp short .done
.invalid:
    mov word [bp-10], 1
.done:
    add sp, 6
    popad
    pop fs
    pop es
    popf
    pop bp
    ret
.deadline:
    mov si, [fs:0x6c]
    mov ecx, 0x01000000
    ret
.within_deadline:
    dec ecx
    jz .expired
    mov ax, [fs:0x6c]
    sub ax, si
    cmp ax, 91
    ret
.expired:
    clc
    ret
.settle:
    mov dx, ALT_PORT
    in al, dx
    in al, dx
    in al, dx
    in al, dx
    ret
