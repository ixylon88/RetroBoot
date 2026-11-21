bits 16
cpu 386
%include "include/memory.inc"
group DGROUP _TEXT CONST CONST2 _DATA _BSS STACK
segment _TEXT public align=16 class=CODE use16
global rb_entry, rb_bss_begin
extern rb_bss_end, rb_file_end, _rb_rescue_runtime, _rb_rescue_run, _rb_putc
%ifdef RB_RESCUE_BACKUP_DISK
extern _rb_backup_disk_run
%define RB_RESCUE_HISTORY_ENTRY _rb_backup_disk_run
%elifdef RB_RESCUE_ATA_TARGET
extern _rb_mbr_target_run
%define RB_RESCUE_HISTORY_ENTRY _rb_mbr_target_run
%elifdef RB_RESCUE_REVIEW
extern _rb_mbr_review_demo
%define RB_RESCUE_HISTORY_ENTRY _rb_mbr_review_demo
%elifdef RB_RESCUE_FIRST_WITNESS
extern _rb_mbr_witness_demo
%define RB_RESCUE_HISTORY_ENTRY _rb_mbr_witness_demo
%elifdef RB_RESCUE_ORIGINAL
extern _rb_mbr_original_demo
%define RB_RESCUE_HISTORY_ENTRY _rb_mbr_original_demo
%elifdef RB_RESCUE_RESERVE
extern _rb_mbr_reserve_demo
%define RB_RESCUE_HISTORY_ENTRY _rb_mbr_reserve_demo
%elifdef RB_RESCUE_RESTART
extern _rb_mbr_restart_demo
%define RB_RESCUE_HISTORY_ENTRY _rb_mbr_restart_demo
%endif
%ifdef RB_RESCUE_MODEL
extern _rb_rescue_selftest
%define RB_RESCUE_ANY_MODEL 1
%endif
%ifdef RB_RESCUE_BACKUP_MODEL
extern _rb_backup_selftest
%define RB_RESCUE_ANY_MODEL 1
%endif
%ifdef RB_RESCUE_ENCODE_MODEL
extern _rb_backup_encode_selftest
%define RB_RESCUE_ANY_MODEL 1
%endif
%ifdef RB_RESCUE_PAYLOAD_MODEL
extern _rb_backup_payload_selftest
%define RB_RESCUE_ANY_MODEL 1
%endif
%ifdef RB_RESCUE_STREAM_MODEL
extern _rb_backup_stream_selftest
%define RB_RESCUE_ANY_MODEL 1
%endif
%ifdef RB_RESCUE_PROVENANCE_MODEL
extern _rb_mbr_provenance_selftest
%define RB_RESCUE_ANY_MODEL 1
%endif
%ifdef RB_RESCUE_VERIFY_MODEL
extern _rb_backup_verify_selftest
%define RB_RESCUE_ANY_MODEL 1
%endif
%ifdef RB_RESCUE_LIVE_MODEL
extern _rb_backup_live_selftest
%define RB_RESCUE_ANY_MODEL 1
%endif
%ifdef RB_RESCUE_RECORD_MODEL
extern _rb_backup_records_selftest
%define RB_RESCUE_ANY_MODEL 1
%endif

%ifdef RB_RESCUE_BOOT_MODEL
extern _rb_backup_boot_selftest
%define RB_RESCUE_ANY_MODEL 1
%endif

%ifdef RB_RESCUE_FILE_MODEL
extern _rb_rescue_file_selftest
%define RB_RESCUE_ANY_MODEL 1
%endif

%ifdef RB_RESCUE_TARGET_MODEL
extern _rb_backup_target_selftest
%define RB_RESCUE_ANY_MODEL 1
%endif
%ifdef RB_RESCUE_PLAN_MODEL
extern _rb_backup_plan_selftest
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
%ifdef RB_RESCUE_HISTORY_ENTRY
    call RB_RESCUE_HISTORY_ENTRY ; boot drive already on stack
    cmp sp, RB_STACK_TOP - 2
    jne failed
    cmp word [RB_STACK_LOW], RB_STACK_GUARD
    jne failed
    mov si, restart_pass
    test ax, ax
    jz .restart_done
    cmp ax, 1
    jne failed
    mov si, restart_blocked
.restart_done:
    call print
    jmp halt
%elifdef RB_RESCUE_ANY_MODEL
%ifdef RB_RESCUE_PROVENANCE_MODEL
    call _rb_mbr_provenance_selftest
%elifdef RB_RESCUE_VERIFY_MODEL
    call _rb_backup_verify_selftest
%elifdef RB_RESCUE_LIVE_MODEL
    call _rb_backup_live_selftest
%elifdef RB_RESCUE_STREAM_MODEL
    call _rb_backup_stream_selftest
%elifdef RB_RESCUE_PAYLOAD_MODEL
    call _rb_backup_payload_selftest
%elifdef RB_RESCUE_ENCODE_MODEL
    call _rb_backup_encode_selftest
%elifdef RB_RESCUE_PLAN_MODEL
    call _rb_backup_plan_selftest
%elifdef RB_RESCUE_TARGET_MODEL
    call _rb_backup_target_selftest
%elifdef RB_RESCUE_FILE_MODEL
    call _rb_rescue_file_selftest
%elifdef RB_RESCUE_BOOT_MODEL
    call _rb_backup_boot_selftest
%elifdef RB_RESCUE_RECORD_MODEL
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
%ifdef RB_RESCUE_BACKUP_DISK
restart_pass db 'RB BACKUP DISK PASS', 13, 10, 0
restart_blocked db 'RB BACKUP DISK BLOCKED', 13, 10, 0
%elifdef RB_RESCUE_ATA_TARGET
restart_pass db 'RB ATA TARGET PASS', 13, 10, 0
restart_blocked db 'RB ATA TARGET BLOCKED', 13, 10, 0
%elifdef RB_RESCUE_REVIEW
restart_pass db 'RB MBR REVIEW PASS', 13, 10, 0
restart_blocked db 'RB MBR REVIEW BLOCKED', 13, 10, 0
%elifdef RB_RESCUE_FIRST_WITNESS
restart_pass db 'RB WITNESS PASS', 13, 10, 0
restart_blocked db 'RB WITNESS BLOCKED', 13, 10, 0
%elifdef RB_RESCUE_ORIGINAL
restart_pass db 'RB ORIGINAL PASS', 13, 10, 0
restart_blocked db 'RB ORIGINAL BLOCKED', 13, 10, 0
%elifdef RB_RESCUE_RESERVE
restart_pass db 'RB MBR RESERVE PASS', 13, 10, 0
restart_blocked db 'RB MBR RESERVE BLOCKED', 13, 10, 0
%elifdef RB_RESCUE_RESTART
restart_pass db 'RB MBR RESTART PASS', 13, 10, 0
restart_blocked db 'RB MBR RESTART BLOCKED', 13, 10, 0
%endif
%ifdef RB_RESCUE_PROVENANCE_MODEL
model_pass db 'RB MBR PROVENANCE PASS', 13, 10, 0
%elifdef RB_RESCUE_VERIFY_MODEL
model_pass db 'RB BACKUP VERIFY PASS', 13, 10, 0
%elifdef RB_RESCUE_LIVE_MODEL
model_pass db 'RB BACKUP LIVE PASS', 13, 10, 0
%elifdef RB_RESCUE_STREAM_MODEL
model_pass db 'RB BACKUP STREAM PASS', 13, 10, 0
%elifdef RB_RESCUE_PAYLOAD_MODEL
model_pass db 'RB BACKUP PAYLOAD PASS', 13, 10, 0
%elifdef RB_RESCUE_ENCODE_MODEL
model_pass db 'RB BACKUP ENCODE PASS', 13, 10, 0
%elifdef RB_RESCUE_PLAN_MODEL
model_pass db 'RB BACKUP PLAN PASS', 13, 10, 0
%elifdef RB_RESCUE_TARGET_MODEL
model_pass db 'RB BACKUP TARGET PASS', 13, 10, 0
%elifdef RB_RESCUE_FILE_MODEL
model_pass db 'RB RESCUE FILE PASS', 13, 10, 0
%elifdef RB_RESCUE_BOOT_MODEL
model_pass db 'RB BACKUP BOOT PASS', 13, 10, 0
%elifdef RB_RESCUE_RECORD_MODEL
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
