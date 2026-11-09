; DS=0, EAX=32-bit LBA, ES:BX=512-byte destination, BX<=FE00h.
; Preserve registers/segments; return CF. At most three read attempts.
; Rebuild the DAP after every BIOS call, including its mutable count field.
; All boot reads use this routine. There is deliberately no write function.
read_sector:
    pushad
    cmp bx, 0xFE00
    ja .bad
    cmp dword [RB_CAPACITY + 4], 0
    jne .bounded
    cmp eax, [RB_CAPACITY]
    jae .bad
.bounded:
    mov di, 3
.retry:
    mov dword [RB_DAP], 0x00010010
    mov [RB_DAP + 4], bx
    mov [RB_DAP + 6], es
    mov [RB_DAP + 8], eax
    mov dword [RB_DAP + 12], 0
    pushad
    push ds
    push es
    mov si, RB_DAP
    mov dl, [RB_DRIVE]
    mov ah, 0x42
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
