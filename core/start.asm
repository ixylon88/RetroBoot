bits 16
cpu 386
%include "include/boot.inc"

group DGROUP _TEXT CONST CONST2 _DATA _BSS STACK
segment _TEXT public align=16 class=CODE use16
global rb_entry, rb_bss_begin
extern rb_bss_end, rb_file_end, _rb_main, _rb_c_mix, _rb_putc, _rb_boot
%ifdef RB_MENU_MODEL_TEST
extern _rb_menu_selftest
%endif
%ifdef RB_SCAN_MODEL_TEST
extern _rb_scan_selftest
%endif
%ifdef RB_VOLUME_MODEL_TEST
extern _rb_volume_selftest
%endif
%ifdef RB_HANDOFF_MODEL_TEST
extern _rb_handoff_selftest
%endif
%ifdef RB_CONFIG_MODEL_TEST
extern _rb_config_selftest
%endif
%ifdef RB_STATE_MODEL_TEST
extern _rb_state_selftest
%endif
%ifdef RB_VISIBILITY_MODEL_TEST
extern _rb_visibility_selftest
%endif
%ifndef RB_TEST
extern _rb_menu_run
%endif

    jmp short rb_entry
    db 'RBS2'
    dw RB_HEADER
    dw rb_file_end, 0           ; includes linked fixture padding; host seals CRC
    dd 0
    dw RB_STAGE2_SEG, rb_entry, 2
    dw rb_bss_begin, rb_bss_end, RB_STACK_LOW, RB_STACK_TOP, 0

rb_entry:
    cli
    mov ax, RB_STAGE2_SEG
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, RB_STACK_TOP
    cld
    mov di, rb_bss_begin        ; linked symbols, never untrusted header bounds
    mov cx, rb_bss_end
    sub cx, di
    xor ax, ax
%ifndef RB_SKIP_BSS_CLEAR
    rep stosb
%endif
    mov word [RB_STACK_LOW], RB_STACK_GUARD

    mov es, ax                 ; AX is still zero, physical loader context
    cmp word [es:RB_CONTEXT], 0x5242
    jne failed
    xor dh, dh
    mov [_rb_boot], dx
    movzx ax, byte [es:RB_IO_MODE]
    mov [_rb_boot + 2], ax
    mov eax, [es:RB_CAPACITY]
    mov [_rb_boot + 4], eax
    mov eax, [es:RB_CAPACITY + 4]
    mov [_rb_boot + 8], eax
    push ds
    pop es
%ifdef RB_BAD_BOOT_CONTEXT
    mov word [_rb_boot + 2], 2
%endif
    sti

    mov si, 0x1357
    mov di, 0x2468
    mov bp, 0x369C
    push word _rb_boot
    call _rb_main
    add sp, 2
    test ax, ax
    jnz failed
    call check_saved

    push word 0x0010
    push word 0x1234
    push word 0xABCD
    call _rb_c_mix
    add sp, 6
    cmp ax, 0xABDD
    jne failed
    cmp dx, 0x1234              ; 32-bit C return in DX:AX
    jne failed
    call check_saved
%ifdef RB_BAD_STACK_GUARD
    mov word [RB_STACK_LOW], 0
%endif
    cmp sp, RB_STACK_TOP
    jne failed
    cmp word [RB_STACK_LOW], RB_STACK_GUARD
    jne failed
%ifdef RB_MENU_MODEL_TEST
    call _rb_menu_selftest
    test ax, ax
    jnz failed
    cmp sp, RB_STACK_TOP
    jne failed
    cmp word [RB_STACK_LOW], RB_STACK_GUARD
    jne failed
    mov si, menu_model_message
    call print
%endif
%ifdef RB_SCAN_MODEL_TEST
    call _rb_scan_selftest
    test ax, ax
    jnz failed
    cmp sp, RB_STACK_TOP
    jne failed
    cmp word [RB_STACK_LOW], RB_STACK_GUARD
    jne failed
    mov si, scan_model_message
    call print
%endif
%ifdef RB_VOLUME_MODEL_TEST
    call _rb_volume_selftest
    test ax, ax
    jnz failed
    cmp sp, RB_STACK_TOP
    jne failed
    cmp word [RB_STACK_LOW], RB_STACK_GUARD
    jne failed
    mov si, volume_model_message
    call print
%endif
%ifdef RB_HANDOFF_MODEL_TEST
    call _rb_handoff_selftest
    test ax, ax
    jnz failed
    cmp sp, RB_STACK_TOP
    jne failed
    cmp word [RB_STACK_LOW], RB_STACK_GUARD
    jne failed
    mov si, handoff_model_message
    call print
%endif
%ifdef RB_CONFIG_MODEL_TEST
    call _rb_config_selftest
    test ax, ax
    jnz failed
    cmp sp, RB_STACK_TOP
    jne failed
    cmp word [RB_STACK_LOW], RB_STACK_GUARD
    jne failed
    mov si, config_model_message
    call print
%endif
%ifdef RB_STATE_MODEL_TEST
    call _rb_state_selftest
    test ax, ax
    jnz failed
    cmp sp, RB_STACK_TOP
    jne failed
    cmp word [RB_STACK_LOW], RB_STACK_GUARD
    jne failed
    mov si, state_model_message
    call print
%endif
%ifdef RB_VISIBILITY_MODEL_TEST
    call _rb_visibility_selftest
    test ax, ax
    jnz failed
    cmp sp, RB_STACK_TOP
    jne failed
    cmp word [RB_STACK_LOW], RB_STACK_GUARD
    jne failed
    mov si, visibility_model_message
    call print
%endif
    mov si, ready_message
    call print
%ifdef RB_TEST
    mov ax, 0x10
    jmp finish
%else
    call _rb_menu_run
    jmp halt
%endif

check_saved:
    cmp si, 0x1357
    jne failed
    cmp di, 0x2468
    jne failed
    cmp bp, 0x369C
    jne failed
    mov ax, ds
    cmp ax, RB_STAGE2_SEG
    jne failed
    ; ES is caller-saved in Watcom cdecl; it is not part of this check.
    mov ax, ss
    cmp ax, RB_STAGE2_SEG
    jne failed
    pushf
    pop ax
    and ax, 0x0600             ; IF=1, DF=0
    cmp ax, 0x0200
    jne failed
    ret

failed:
    ; A failed stack/segment check must still leave a usable diagnostic path.
    cli
    mov ax, RB_STAGE2_SEG
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, RB_STACK_TOP
    cld
    sti
    mov si, failed_message
    call print
%ifdef RB_TEST
    mov ax, 0x11
finish:
    mov dx, 0xF4
    out dx, ax
%endif
halt:
    cli
.wait:
    hlt
    jmp .wait

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

ready_message db 'RetroBoot Stage 2 ready', 13, 10, 'RB HDD PASS', 13, 10, 0
failed_message db 'RB C STARTUP ERROR', 13, 10, 0
%ifdef RB_MENU_MODEL_TEST
menu_model_message db 'RB MENU MODEL PASS', 13, 10, 0
%endif
%ifdef RB_SCAN_MODEL_TEST
scan_model_message db 'RB SCAN MODEL PASS', 13, 10, 0
%endif
%ifdef RB_VOLUME_MODEL_TEST
volume_model_message db 'RB VOLUME MODEL PASS', 13, 10, 0
%endif
%ifdef RB_HANDOFF_MODEL_TEST
handoff_model_message db 'RB HANDOFF MODEL PASS', 13, 10, 0
%endif

%ifdef RB_CONFIG_MODEL_TEST
config_model_message db 'RB CONFIG MODEL PASS', 13, 10, 0
%endif

%ifdef RB_STATE_MODEL_TEST
state_model_message db 'RB STATE MODEL PASS', 13, 10, 0
%endif

%ifdef RB_VISIBILITY_MODEL_TEST
visibility_model_message db 'RB VISIBILITY MODEL PASS', 13, 10, 0
%endif

segment CONST public align=2 class=DATA use16
segment CONST2 public align=2 class=DATA use16
segment _DATA public align=2 class=DATA use16
segment _BSS public align=2 class=BSS use16
rb_bss_begin:
segment STACK stack align=16 class=STACK use16
    resb RB_STACK_TOP - RB_STACK_LOW
