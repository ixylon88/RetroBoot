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
; 7=AH48 non-512 sectors, 8=AH48 short parameter buffer, 9=zero capacity.
; Rescue only: 10=one floppy payload read failure, 11=persistent failure.
; Rescue only: 19=one changed FAT32 tail byte in the second payload pass.
    dw 0xAA55
%if RB_ROM_MODE >= 17 && RB_ROM_MODE <= 18
    db 2                       ; extra block for a replacement saved sector
%else
    db 1
%endif
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
%ifdef RB_RESCUE_TRACE
    ; Rescue-only instrumentation includes attempted floppy/HDD writes.
    cmp ah, 0x03
    je .write
    cmp ah, 0x05
    je .write
    cmp ah, 0x0B
    je .write
    cmp ah, 0x43
    jne .read_only
.write:
    push ax
    mov al, '!'
    out 0xE9, al
    mov al, 'W'
    out 0xE9, al
    mov al, 10
    out 0xE9, al
    pop ax
.read_only:
    ; File-reader attempts only: the loader uses a different destination.
    cmp dl, 0
    jne .trace_done
    cmp ah, 2
    jne .trace_done
    cmp bx, 0x1000
    jne .trace_done
    push ax
    mov ax, es
    test ax, ax
    pop ax
    jnz .trace_done
    pushad
    mov al, ch
    xor ah, ah
    shl ax, 1
    mov bl, dh
    xor bh, bh
    add ax, bx
    mov bx, 18
    mul bx
    mov bl, cl
    xor bh, bh
    add ax, bx
    dec ax
    mov bx, ax
    mov al, '%'
    out 0xE9, al
    mov cx, 4
.trace_digit:
    rol bx, 4
    mov al, bl
    and al, 15
    call hex
    loop .trace_digit
    mov al, 10
    out 0xE9, al
    popad
.trace_done:
%if RB_ROM_MODE >= 16 && RB_ROM_MODE <= 18
    ; After the second HDD discovery, alter one saved sector returned
    ; by the BIOS. The physical floppy remains unchanged. LBA 372 is the
    ; synthetic file's first cluster, not the rescue program's loader.
    cmp byte [cs:change_pending - handler], 0
    je .saved_done
    cmp dl, 0
    jne .saved_done
    cmp ah, 2
    jne .saved_done
%if RB_ROM_MODE == 18
    cmp cx, RB_SAVED_CX         ; generated original-payload address
%else
    cmp cx, 0x0A0D              ; LBA 372, cylinder 10, sector 13
%endif
    jne .saved_done
%if RB_ROM_MODE == 18
    cmp dh, RB_SAVED_DH
%else
    cmp dh, 0
%endif
    jne .saved_done
    mov byte [cs:change_pending - handler], 0
    popf
    pushf
    call far [cs:old13 - handler]
    jc .saved_return
%if RB_ROM_MODE == 16
    xor byte [es:bx + 508], 1   ; invalid header CRC on the final file check
%else
    push ds
    push si
    push di
    push cx
    push cs
    pop ds
    mov si, replacement - handler
    mov di, bx
    mov cx, 256
    cld
    rep movsw                  ; valid sector with a recalculated trailing CRC
    pop cx
    pop di
    pop si
    pop ds
%endif
.saved_return:
    pushf                      ; common return helpers expect the entry PUSHF
    jc rejected
    jmp accepted
.saved_done:
%endif
%if RB_ROM_MODE >= 10 && RB_ROM_MODE <= 13
    cmp dl, 0
    jne .floppy_done
    cmp ah, 2
    jne .floppy_done
%if RB_ROM_MODE < 12
    cmp cx, 16                 ; LBA 33: cylinder 0, head 1, sector 16
%else
    cmp cx, 2                  ; LBA 19: root directory, only read by the file UI
%endif
    jne .floppy_done
    cmp dh, 1
    jne .floppy_done
%if RB_ROM_MODE == 10 || RB_ROM_MODE == 12
    cmp byte [cs:floppy_failures - handler], 0
    jne .floppy_done
%endif
    inc byte [cs:floppy_failures - handler]
    push ax
    mov al, '!'
    out 0xE9, al
    mov al, 'F'
    out 0xE9, al
    mov al, 10
    out 0xE9, al
    pop ax
    jmp rejected
.floppy_done:
%endif
%endif
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
%if RB_ROM_MODE >= 6 && RB_ROM_MODE <= 9
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
%elif RB_ROM_MODE == 8
    mov word [si], 24
    jmp accepted
%else
    mov dword [si + 16], 0
    mov dword [si + 20], 0
    jmp accepted
%endif
%endif
%if RB_ROM_MODE >= 14 && RB_ROM_MODE <= 18
    cmp ah, 0x48
    jne chain
    inc byte [cs:probe_count - handler]
    cmp byte [cs:probe_count - handler], 2
    jb chain
    mov byte [cs:probe_count - handler], 0
%if RB_ROM_MODE == 14
    mov word [si], 26
    mov dword [si + 16], 262145
    mov dword [si + 20], 0
    mov word [si + 24], 512
    jmp accepted
%elif RB_ROM_MODE == 15
    jmp rejected
%else
    mov byte [cs:change_pending - handler], 1
%endif
%endif
%if RB_ROM_MODE == 19
    cmp ah, 0x48
    jne .payload_read
    mov byte [cs:payload_count - handler], 0
    jmp chain
.payload_read:
    cmp ah, 0x42
    jne chain
    cmp dword [si + 8], 131103 ; last reserved sector, validation then payload
    jne chain
    cmp dword [si + 12], 0
    jne chain
    inc byte [cs:payload_count - handler]
    cmp byte [cs:payload_count - handler], 4
    jne chain
    popf
    pushf
    call far [cs:old13 - handler]
    jc .payload_return
    push es
    push bx
    les bx, [si + 4]
    xor byte [es:bx + 100], 1  ; only the returned buffer changes, never the HDD
    pop bx
    pop es
.payload_return:
    pushf
    jc rejected
    jmp accepted
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
%if RB_ROM_MODE >= 10 && RB_ROM_MODE <= 13
floppy_failures: db 0
%endif
%if RB_ROM_MODE >= 14 && RB_ROM_MODE <= 18
probe_count: db 0
change_pending: db 0
%endif
%if RB_ROM_MODE == 19
payload_count: db 0
%endif
%if RB_ROM_MODE >= 17 && RB_ROM_MODE <= 18
replacement: incbin RB_REPLACEMENT_SECTOR
%endif
old13: dd 0                   ; populated in reserved RAM, never written in ROM
%if RB_ROM_MODE >= 17 && RB_ROM_MODE <= 18
    times 1023 - ($ - $$) db 0
%else
    times 511 - ($ - $$) db 0
%endif
    db 0                       ; byte checksum, sealed by the host builder
