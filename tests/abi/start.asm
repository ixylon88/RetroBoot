bits 16
cpu 386
%include "include/memory.inc"

; Small-model objects, grouped into one segment by our own startup/link script.
group DGROUP _TEXT CONST CONST2 _DATA _BSS STACK
segment _TEXT public align=16 class=CODE use16
global rb_entry, rb_bss_begin
extern rb_bss_end, rb_file_end, _rb_probe, _rb_c_mix
extern _rb_initialized_word, _rb_bss_word, _rb_putc

    jmp short rb_entry
    db 'RBABI01', 0
    dw RB_HEADER_BYTES, rb_entry, rb_bss_begin, rb_bss_end
    dw RB_LOAD_SEG, RB_STACK_LOW, RB_STACK_TOP, rb_file_end
    dw 1, _rb_initialized_word, _rb_bss_word

rb_entry:
    cli
    mov ax, RB_LOAD_SEG
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, RB_STACK_TOP
    cld
    mov di, rb_bss_begin
    mov cx, rb_bss_end
    sub cx, di
    xor ax, ax
%ifndef RB_SKIP_BSS_CLEAR
    rep stosb
%endif
    mov word [RB_STACK_LOW], RB_STACK_GUARD
    sti

    ; Exercise callee-saved SI/DI/BP and caller-cleaned arguments in both calls.
    mov si, 0x1357
    mov di, 0x2468
    mov bp, 0x369C
    xor dh, dh
    push dx                         ; BIOS boot drive, widened to a word
    call _rb_probe
    add sp, 2
    test ax, ax
    jnz failed
    call check_saved

    push word 0x0010                ; rightmost argument first
    push word 0x1234                ; high word of the 32-bit argument
    push word 0xABCD                ; low word nearest the return address
    call _rb_c_mix
    add sp, 6
    cmp ax, 0xABDD
    jne failed
    cmp dx, 0x1234                  ; 32-bit return value is DX:AX
    jne failed
    call check_saved
    cmp sp, RB_STACK_TOP
    jne failed
    cmp word [RB_STACK_LOW], RB_STACK_GUARD
    jne failed
    mov si, passed_message
    call print
    mov ax, 0x10
    jmp finish

check_saved:
    cmp si, 0x1357
    jne failed
    cmp di, 0x2468
    jne failed
    cmp bp, 0x369C
    jne failed
    ret

failed:
    mov si, failed_message
    call print
    mov ax, 0x11
finish:
    mov dx, 0xF4                    ; test-only QEMU isa-debug-exit device
    out dx, ax
    cli
.halt:
    hlt
    jmp .halt

print:
    lodsb
    test al, al
    jz .done
    xor ah, ah
    push ax
    call _rb_putc
    add sp, 2
    jmp print
.done:
    ret

passed_message db 'RB ABI PASS', 13, 10, 0
failed_message db 'RB ABI FAIL', 13, 10, 0

segment CONST public align=2 class=DATA use16
segment CONST2 public align=2 class=DATA use16
segment _DATA public align=2 class=DATA use16
segment _BSS public align=2 class=BSS use16
rb_bss_begin:

segment STACK stack align=16 class=STACK use16
    resb RB_STACK_TOP - RB_STACK_LOW
