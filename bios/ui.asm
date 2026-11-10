; VGA text output and BIOS keyboard/BDA wrappers; no disk service or writes.
bits 16
cpu 386
%include "include/boot.inc"
segment _TEXT public align=16 class=CODE use16
global _rb_video_init, _rb_video_fill, _rb_video_text, _rb_loader_copy
global _rb_key_poll, _rb_ticks, _rb_idle, _rb_debug_putc

%macro save 0
    push bp
    mov bp, sp
    pushf
    push ds
    push es
    pushad
%endmacro
%macro restore 0
    popad
    pop es
    pop ds
    popf
    pop bp
    ret
%endmacro

_rb_video_init:
    save
    mov ax, 0x0003             ; VGA 80x25 color text, display page zero
    int 0x10
    mov ah, 0x01
    mov cx, 0x2000             ; hide cursor; highlight shows the selection
    int 0x10
    restore

_rb_video_fill:
    save
    mov di, [ss:bp + 4]
    mov cx, [ss:bp + 6]
    cmp di, 2000
    jae .done
    mov ax, 2000
    sub ax, di
    cmp cx, ax
    ja .done
    shl di, 1
    mov ax, 0xB800
    mov es, ax
    mov ax, [ss:bp + 8]
    cld
    rep stosw
.done:
    restore

_rb_video_text:
    save
    mov di, [ss:bp + 4]
    cmp di, 2000
    jae .done
    mov cx, 2000
    sub cx, di
    shl di, 1
    mov si, [ss:bp + 6]
    mov ax, 0xB800
    mov es, ax
    mov ah, [ss:bp + 8]
    cld
.next:
    lodsb
    test al, al
    jz .done
    stosw
    loop .next
.done:
    restore

_rb_loader_copy:
    save
    mov di, [ss:bp + 4]        ; near pointer may refer to the C stack (DS=SS)
    push ds
    pop es
    xor ax, ax
    mov ds, ax
    mov si, RB_HEADS
    mov cx, 8
    cld
    rep movsb
    mov si, RB_MBR
    mov cx, 512
    rep movsb
    restore

_rb_key_poll:
    save
    mov ah, 0x01
    push bp
    int 0x16
    pop bp
    jz .empty
    xor ah, ah
    push bp
    int 0x16
    pop bp
    jmp .result
.empty:
    mov ax, 0xFFFF             ; preserve AX=0000 as a real keyboard event
.result:
    mov [ss:bp - 10], ax       ; low word of saved EAX in the PUSHAD frame
    restore

_rb_ticks:
    save
    xor ax, ax
    mov es, ax
    cli
    mov eax, [es:0x046C]       ; BIOS ticks since midnight, no midnight-flag reset
    mov [ss:bp - 10], ax
    shr eax, 16
    mov [ss:bp - 18], ax       ; low word of saved EDX: C/16 returns DX:AX
    restore

_rb_idle:
    sti
    hlt                       ; wake on timer/keyboard IRQ, no busy spinning
    ret

_rb_debug_putc:
    push bp
    mov bp, sp
    push ax
    mov ax, [ss:bp + 4]
    out 0xE9, al               ; diagnostics must not alter the visible menu
    pop ax
    pop bp
    ret
