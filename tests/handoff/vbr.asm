; Independent 512-byte T07 target. Fixture-specific BPB and partition entry.
bits 16
cpu 386
org 0x7C00
%include "include/handoff.inc"
%include "handoff_fixture.inc"
    jmp short entry
    nop
%ifdef RB_TEST_FAT32
    times 90-($-$$) db 0       ; filled with the fixture's FAT32 BPB before enrollment
%else
    db 'RBT07   '
    dw 512
    db 1
    dw 1
    db 2
    dw 512, 0
    db 0xF8
    dw 20, 63, 255
    dd RB_TEST_LBA, 5073
    db 0x80, 0, 0x29
    dd 0x54303731
    db 'RB T07 TEST', 'FAT16   '
%endif
entry:
    mov [cs:RB_HANDOFF_RECEIPT + 14], sp
    pushf
    pop word [cs:RB_HANDOFF_RECEIPT + 4]
    mov [cs:RB_HANDOFF_RECEIPT + 6], cs
    mov [cs:RB_HANDOFF_RECEIPT + 8], ds
    mov [cs:RB_HANDOFF_RECEIPT + 10], es
    mov [cs:RB_HANDOFF_RECEIPT + 12], ss
    mov [cs:RB_HANDOFF_RECEIPT + 16], si
    mov [cs:RB_HANDOFF_RECEIPT + 18], dx
    mov [cs:RB_HANDOFF_RECEIPT + 20], fs
    mov [cs:RB_HANDOFF_RECEIPT + 22], gs
    mov dword [cs:RB_HANDOFF_RECEIPT], 'RBH1'
    smsw ax
    test ax, 1
    jnz failed
    mov ax, cs
    mov bx, ds
    or ax, bx
    mov bx, es
    or ax, bx
    mov bx, ss
    or ax, bx
    mov bx, fs
    or ax, bx
    mov bx, gs
    or ax, bx
    jnz failed
    cmp sp, RB_HANDOFF_STACK
    jne failed
    cmp dx, 0x0080
    jne failed
    cmp si, RB_HANDOFF_ENTRY
    jne failed
    mov ax, [RB_HANDOFF_RECEIPT + 4]
    and ax, 0x0600
    cmp ax, 0x0200
    jne failed
    call .address
.address:
    pop ax
    mov [RB_HANDOFF_RECEIPT + 24], ax
    cmp ax, .address
    jne failed
    cmp word [0x7DFE], 0xAA55
    jne failed
    mov di, expected_entry
    mov cx, 8
    repe cmpsw
    jne failed
    mov word [RB_HANDOFF_RECEIPT + 26], 0
    mov si, passed
    jmp display
failed:
    ; Fault fixtures still have a usable stack; normalize it for diagnostics.
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, RB_HANDOFF_STACK
    cld
    mov word [RB_HANDOFF_RECEIPT + 26], 1
    mov si, rejected
display:
    mov ax, 3
    int 0x10
    call print
    mov si, restart
    call print
    mov al, 10
    out 0xE9, al                ; final newline only after the visible page is complete
    sti
.halt:
    hlt
    jmp .halt
print:
    lodsb
    test al, al
    jz .done
    out 0xE9, al
    mov ah, 0x0E
    mov bx, 7
    int 0x10
    jmp print
.done:
    ret
expected_entry: db RB_TEST_ENTRY_BYTES
passed: db 'RB HANDOFF PASS', 13, 10, 0
rejected: db 'RB HANDOFF FAIL', 13, 10, 0
restart: db 'Test VBR reached. Reboot to return.', 13, 10, 0
    times 510-($-$$) db 0
    dw 0xAA55
