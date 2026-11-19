; Fixed 1440 KiB A: I/O. Each test writer has its own bounded LBA range.
bits 16
cpu 386
%include "include/boot.inc"
segment _TEXT public align=16 class=CODE use16
%ifdef RB_WITNESS_WRITE
%define RB_FIXTURE_WRITE 1
%elifdef RB_RESERVATION_WRITE
%define RB_FIXTURE_WRITE 1
%elifdef RB_ORIGINAL_WRITE
%define RB_FIXTURE_WRITE 1
%endif
%ifdef RB_FIXTURE_WRITE
global _rb_fixture_floppy_write
_rb_fixture_floppy_write:
%else
global _rb_floppy_read
_rb_floppy_read:
%endif
    push bp
    mov bp, sp
    pushf
    push ds
    push es
    pushad
    mov eax, [ss:bp + 4]
    cmp eax, 2880
    jae .bad
    cmp word [ss:bp + 8], 0xFE00
    ja .bad
    mov bx, [ss:bp + 10]
    cmp word [bx], 0
    jne .bad
    mov si, ax
%ifdef RB_FIXTURE_WRITE
%ifdef RB_WITNESS_WRITE
    cmp ax, 3                   ; first commit header on the enrolled recovery carrier
    je .buffer
    cmp ax, 2877                ; header and original in the separate FAT12 witness
    jb .bad
    cmp ax, 2878
    ja .bad
%elifdef RB_ORIGINAL_WRITE
    cmp ax, 1                   ; dedicated recovery carrier: header and original
    jb .bad
    cmp ax, 2
    ja .bad
%else
    cmp ax, 2877                ; reserved witness header on the owned boot floppy
    je .buffer
    cmp ax, 3                   ; alternate commit headers and payloads on the carrier
    jb .bad
    cmp ax, 6
    ja .bad
%endif
.buffer:
    mov dx, si
    mov si, [ss:bp + 8]
    xor ax, ax
    mov es, ax
    mov di, RB_BUFFER
    mov cx, 256
    cld
    rep movsw
    mov si, dx
%else
    mov di, 3
%endif
.retry:
    mov ax, si
    xor dx, dx
    mov cx, 18
    div cx
    mov cl, dl
    inc cl
    xor dx, dx
    mov bx, 2
    div bx
    mov ch, al
    mov dh, dl
    xor dl, dl
    xor ax, ax
    mov es, ax
    mov bx, RB_BUFFER
%ifdef RB_FIXTURE_WRITE
    mov ax, 0x0301
%else
    mov ax, 0x0201
%endif
    pushad
    push ds
    push es
    stc
    int 0x13
    pop es
    pop ds
    popad
%ifdef RB_FIXTURE_WRITE
    jc .bad                     ; an ambiguous write is never retried here
    xor ax, ax
    jmp .done
%else
    jnc .copy
    pushad
    push ds
    push es
    xor ax, ax
    xor dl, dl
    int 0x13
    pop es
    pop ds
    popad
    dec di
    jnz .retry
%endif
.bad:
    mov ax, 1
    jmp .done
%ifndef RB_FIXTURE_WRITE
.copy:
    push ds
    pop es
    xor ax, ax
    mov ds, ax
    mov si, RB_BUFFER
    mov di, [ss:bp + 8]
    mov cx, 256
    cld
    rep movsw
    xor ax, ax
%endif
.done:
    mov [ss:bp - 10], ax
    popad
    pop es
    pop ds
    popf
    pop bp
    ret
