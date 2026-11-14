bits 16
cpu 386
%include "include/memory.inc"
group DGROUP _TEXT CONST CONST2 _DATA _BSS STACK
segment _TEXT public align=16 class=CODE use16
global rb_entry, rb_bss_begin
extern rb_bss_end, rb_file_end, _rb_rescue_runtime, _rb_rescue_run, _rb_putc
%ifdef RB_RESCUE_MODEL
extern _rb_rescue_selftest
%define RB_RESCUE_ANY_MODEL 1
%endif
%ifdef RB_RESCUE_BACKUP_MODEL
extern _rb_backup_selftest
%define RB_RESCUE_ANY_MODEL 1
%endif
%ifdef RB_RESCUE_RECORD_MODEL
extern _rb_backup_records_selftest
%define RB_RESCUE_ANY_MODEL 1
%endif

    jmp short rb_entry
    db 'RBRS'
    dw 32
    dw rb_file_end, 0
    dd 0                       ; host-sealed body CRC; VBR pins whole-file CRC
    dw RB_LOAD_SEG, rb_entry, 1
    dw rb_bss_begin, rb_bss_end, RB_STACK_LOW, RB_STACK_TOP, 0
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
%ifndef RB_RESCUE_BAD_BSS
    rep stosb
%endif
    mov word [RB_STACK_LOW], RB_STACK_GUARD
    sti
    xor dh, dh
    push dx                    ; preserve boot-medium identity across C calls
    call _rb_rescue_runtime
    test ax, ax
    jnz failed
    cmp word [RB_STACK_LOW], RB_STACK_GUARD
    jne failed
%ifdef RB_RESCUE_ANY_MODEL
%ifdef RB_RESCUE_RECORD_MODEL
    call _rb_backup_records_selftest
%elifdef RB_RESCUE_BACKUP_MODEL
    call _rb_backup_selftest
%else
    call _rb_rescue_selftest
%endif
    test ax, ax
    jnz failed
    cmp sp, RB_STACK_TOP - 2
    jne failed
    cmp word [RB_STACK_LOW], RB_STACK_GUARD
    jne failed
    mov si, model_pass
    call print
    jmp halt
%else
    call _rb_rescue_run
%endif
failed:
    cli
    mov ax, RB_LOAD_SEG
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, RB_STACK_TOP
    cld
    sti
    mov si, failure
    call print
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
failure db 'RB RESCUE STARTUP ERROR', 13, 10, 0
%ifdef RB_RESCUE_RECORD_MODEL
model_pass db 'RB BACKUP RECORDS PASS', 13, 10, 0
%elifdef RB_RESCUE_BACKUP_MODEL
model_pass db 'RB BACKUP MODEL PASS', 13, 10, 0
%elifdef RB_RESCUE_MODEL
model_pass db 'RB RESCUE MODEL PASS', 13, 10, 0
%endif
segment CONST public align=2 class=DATA use16
segment CONST2 public align=2 class=DATA use16
segment _DATA public align=2 class=DATA use16
segment _BSS public align=2 class=BSS use16
rb_bss_begin:
segment STACK stack align=16 class=STACK use16
    resb RB_STACK_TOP - RB_STACK_LOW
