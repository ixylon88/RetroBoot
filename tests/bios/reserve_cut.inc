; Test ROM only. A stopped guest is killed and cold-booted from the same files.
    cmp dl, 0
    jne .inject_done
    cmp byte [cs:cut_mode - handler], 6
    jne .count_write
    cmp byte [cs:write_count - handler], 3
    jne .count_write
    cmp ax, 0x0201
    jne .count_write
    cmp cx, 0x4f12              ; LBA 2879, last witness payload
    jne .inject_done
    cmp dh, 1
    jne .inject_done
    inc byte [cs:closing_reads - handler]
    cmp byte [cs:closing_reads - handler], 2
    jne .inject_done
    stc
    pushf
    call far [cs:old13 - handler]
    jc rejected
    xor byte [es:bx + 77], 1    ; change only the final successful return buffer
    jmp accepted
.count_write:
    cmp ax, 0x0301
    jne .inject_done
    inc byte [cs:write_count - handler]
    push ax
    mov al, [cs:cut_write - handler]
    cmp al, [cs:write_count - handler]
    pop ax
    jne .inject_done
    cmp byte [cs:cut_mode - handler], 6
    je .inject_done
    cmp byte [cs:cut_mode - handler], 1
    je .cut
    cmp byte [cs:cut_mode - handler], 4
    je accepted                ; lost write, reported as successful
    cmp byte [cs:cut_mode - handler], 3
    jne .apply
    pushad
    push ds
    push es
    push es
    push bx
    push cs
    pop es
    mov bx, 1024
    mov ax, 0x0201
    stc
    pushf
    call far [cs:old13 - handler]
    pop di
    pop es
    jc .read_failed
    push cs
    pop ds
    mov si, 1024 + 128
    add di, 128
    mov cx, 512 - 128          ; only the first 128 new bytes reach the disk
    cld
    rep movsb
    pop es
    pop ds
    popad
.apply:
    stc
    pushf
    call far [cs:old13 - handler]
    jc rejected
    cmp byte [cs:cut_mode - handler], 5
    je rejected                ; completed sector with ambiguous return status
.cut:
    mov al, '~'
    out 0xe9, al
    mov al, 10
    out 0xe9, al
    cli
.off:
    hlt
    jmp .off
.read_failed:
    pop es
    pop ds
    popad
    jmp rejected
.inject_done:
