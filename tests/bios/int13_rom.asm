; Test-only option ROM: record INT 13h functions and emulate missing/bad BIOS
; capabilities. The production MBR is never patched to force a code branch.
bits 16
cpu 386
org 0
%ifndef RB_ROM_MODE
    %define RB_ROM_MODE 0
%endif
; 0=passthrough, 1=no EDD, 2=bad EDD signature, 3=no extended-read bit,
; 4=no EDD + AH08 error, 5=no EDD + zero sectors, 6=AH48 error,
; 7=AH48 non-512 sectors, 8=AH48 short parameter buffer.
    dw 0xAA55
    db 1                       ; one 512-byte ROM block
    jmp init
init:
    pushf
    pushad
    push ds
    push es
    xor ax, ax
    mov ds, ax
    cli
    dec word [0x0413]          ; reserve one KiB below conventional-memory top
    mov ax, [0x0413]
    shl ax, 6
    mov es, ax
    mov eax, [0x004C]
    mov [es:old13 - handler], eax
    mov word [0x004C], 0
    mov [0x004E], es
    push cs
    pop ds
    mov si, handler
    xor di, di
    mov cx, old13 - handler
    cld
    rep movsb
    pop es
    pop ds
    popad
    popf
    retf
handler:
    pushf
    cmp dl, 0x80
    jne chain
    push ax
    mov al, '@'
    out 0xE9, al
    mov al, ah
    shr al, 4
    call hex
    mov al, ah
    and al, 15
    call hex
    mov al, 10
    out 0xE9, al
    pop ax
%if RB_ROM_MODE >= 1 && RB_ROM_MODE <= 5
    cmp ah, 0x41
    je probe
    cmp ah, 0x42
    je rejected
    cmp ah, 0x48
    je rejected
%endif
%if RB_ROM_MODE == 4 || RB_ROM_MODE == 5
    cmp ah, 8
    jne chain
%if RB_ROM_MODE == 4
    mov cx, 0x803F             ; otherwise usable 129/16/63 geometry
    mov dh, 15                 ; CF alone must make this response invalid
    jmp rejected
%else
    xor cx, cx
    xor dh, dh
    jmp accepted
%endif
%endif
%if RB_ROM_MODE >= 6
    cmp ah, 0x48
    jne chain
    ; Keep every unrelated field valid: each test must exercise its own guard.
    mov word [si], 26
    mov dword [si + 16], 131072
    mov dword [si + 20], 0
    mov word [si + 24], 512
%if RB_ROM_MODE == 6
    jmp rejected
%elif RB_ROM_MODE == 7
    mov word [si + 24], 4096
    jmp accepted
%else
    mov word [si], 24
    jmp accepted
%endif
%endif
chain:
    popf
    jmp far [cs:old13 - handler]
probe:
%if RB_ROM_MODE == 2
    xor bx, bx
    mov cx, 1
    jmp accepted
%elif RB_ROM_MODE == 3
    mov bx, 0xAA55
    xor cx, cx
    jmp accepted
%else
    mov bx, 0xAA55             ; plausible outputs must not override CF=1
    mov cx, 1
    jmp rejected
%endif
rejected:
    popf
    mov ah, 1
    push bp
    mov bp, sp
    or word [ss:bp + 6], 1
    pop bp
    iret
accepted:
    popf
    xor ah, ah
    push bp
    mov bp, sp
    and word [ss:bp + 6], 0xFFFE
    pop bp
    iret
hex:
    add al, '0'
    cmp al, '9'
    jbe .out
    add al, 7
.out:
    out 0xE9, al
    ret
old13: dd 0                   ; populated in reserved RAM, never written in ROM
    times 511 - ($ - $$) db 0
    db 0                       ; byte checksum, sealed by the host builder
