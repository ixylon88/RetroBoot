; Exclusive, polled PIO on the two legacy IDE masters. The primary master
; exposes only IDENTIFY and a read of LBA 0. Only the secondary entry point
; can write its six pre-enrolled recovery records. The separate backup build
; enables primary LBA28 reads and a disjoint secondary store at LBA 8 and 16..2063.
; The restore build can write only the primary master at fixed LBA 0.
bits 16
cpu 386
segment _TEXT public align=16 class=CODE use16
global _rb_ata_identify_words, _rb_ata_read_sector, _rb_ata_write_recovery

%ifdef RB_BACKUP_DISK
global _rb_ata_source_read, _rb_ata_store_read
_rb_ata_source_read:            ; uint32 LBA, buffer; primary master, read-only
    mov al, 0x21
    jmp short transfer
_rb_ata_store_read:             ; uint16 LBA, buffer; secondary master, 7..2063
    mov al, 0x22
    jmp short transfer
%ifdef RB_RESTORE_MBR
global _rb_ata_restore_mbr
_rb_ata_restore_mbr:            ; buffer only; fixed primary master and LBA 0
    mov al, 0x32
    jmp short transfer
%else
global _rb_ata_store_write
_rb_ata_store_write:            ; uint16 LBA, buffer; secondary master, 8 and 16..2063
    mov al, 0x31
    jmp short transfer
%endif
%endif
_rb_ata_identify_words:         ; channel, buffer
    mov al, 0xec
    jmp short transfer
_rb_ata_read_sector:            ; channel, LBA, buffer
    mov al, 0x20
    jmp short transfer
_rb_ata_write_recovery:         ; LBA, buffer (no caller-supplied channel)
%ifdef RB_BACKUP_DISK
    mov ax, 1                   ; this build cannot write the six history records
    ret
%else
    mov al, 0x30
%endif
transfer:
    push bp
    mov bp, sp
    pushf
    push es
    push fs
    pushad
%ifdef RB_BACKUP_DISK
    sub sp, 8
%define LONG_LBA dword [ss:bp-46]
%define IO_LBA byte [ss:bp-46]
%else
    sub sp, 6
%define IO_LBA byte [ss:bp-44]
%endif
%define TASK_PORT word [ss:bp-40]
%define ALT_PORT  word [ss:bp-42]
    mov bl, al
    xor cx, cx
    mov ax, [bp+4]
    mov di, [bp+6]
%ifdef RB_BACKUP_DISK
    mov LONG_LBA, 0
    cmp bl, 0x21
    jne .not_source
    mov ecx, [bp+4]
    cmp ecx, 0x0fffffff
    ja .invalid
    mov LONG_LBA, ecx
    mov di, [bp+8]
    xor ax, ax
    mov bl, 0x20
    jmp short .buffer
.not_source:
    cmp bl, 0x22
    je .store_read
%ifdef RB_RESTORE_MBR
    cmp bl, 0x32
    jne .legacy
    mov di, ax                  ; sole argument is the sector buffer
    xor ax, ax                  ; primary master, LONG_LBA already zero
    mov bl, 0x30
    jmp short .buffer
%else
    cmp bl, 0x31
    jne .legacy
    cmp ax, 8
    je .store_write
    cmp ax, 16
    jb .invalid
.store_write:
    mov bl, 0x30
    jmp short .store
%endif
.store_read:
    cmp ax, 7
    jb .invalid
    mov bl, 0x20
.store:
    cmp ax, 2063
    ja .invalid
    mov word [ss:bp-46], ax
    mov ax, 1
    jmp short .buffer
.legacy:
%endif
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
    mov IO_LBA, cl
.buffer:
    cmp di, 0xfe00
    ja .invalid
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
%ifdef RB_BACKUP_DISK
    mov al, [ss:bp-43]          ; high four LBA28 bits
    or al, 0xe0
%else
    mov al, 0xe0                ; LBA, master, high nibble zero
%endif
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
%ifdef RB_BACKUP_DISK
    mov al, [ss:bp-45]
%else
    xor al, al
%endif
    out dx, al
    inc dx
%ifdef RB_BACKUP_DISK
    mov al, [ss:bp-44]
%endif
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
    mov bl, 0xe7                ; FLUSH CACHE on the same master
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
%ifdef RB_BACKUP_DISK
    add sp, 8
%else
    add sp, 6
%endif
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
