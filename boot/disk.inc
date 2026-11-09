; DS=0, EAX=32-bit LBA, ES:BX=512-byte destination, BX<=FE00h.
; Preserve registers/segments; return CF, DF=0. At most three attempts.
; The MBR selects EDD or CHS once. Never switch after an I/O error.
read_sector:
    pushad
%ifndef RB_FIXED_VBR_BUFFER
    cmp bx, 0xFE00
    ja .bad
%endif
    cmp dword [RB_CAPACITY + 4], 0
    jne .bounded
    cmp eax, [RB_CAPACITY]
    jae .bad
.bounded:
    mov di, 3
.retry:
    pushad
    push ds
    push es
    cmp byte [RB_IO_MODE], 0
    je .chs
    mov dword [RB_DAP], 0x00010010
    mov [RB_DAP + 4], bx
    mov [RB_DAP + 6], es
    mov [RB_DAP + 8], eax
    mov dword [RB_DAP + 12], 0
    mov si, RB_DAP
    mov ah, 0x42
    jmp .read
.chs:
    ; The capacity bound above guarantees cylinder < reported count <=1024.
    ; AH=08h geometry, never the BPB or partition-entry CHS bytes.
    xor edx, edx
    div dword [RB_SPT]
    mov cl, dl
    inc cl
    xor edx, edx
    div dword [RB_HEADS]
    mov dh, dl
    mov ch, al
    shl ah, 6
    or cl, ah
    mov ax, 0x0201             ; exactly one sector, no track crossing
.read:
    mov dl, [RB_DRIVE]
    stc
    int 0x13
    pop es
    pop ds
    popad
    jnc .done
    pushad
    push ds
    push es
    mov dl, [RB_DRIVE]
    xor ah, ah
    int 0x13
    pop es
    pop ds
    popad
    dec di
    jnz .retry
.bad:
    stc
.done:
    popad
    cld
    ret
