; SI points to a NUL-terminated diagnostic in DS=0. Never hand off on error.
fatal:
    cld
.print:
    lodsb
    test al, al
    jz .stop
    out 0xE9, al
    pushad
    push ds
    push es
    mov ah, 0x0E
    mov bx, 7
    int 0x10
    pop es
    pop ds
    popad
    jmp .print
.stop:
%ifdef RB_TEST
    mov dx, 0xF4
    mov ax, 0x11
    out dx, ax
%endif
    cli
.halt:
    hlt
    jmp .halt
