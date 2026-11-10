bits 16
cpu 386
segment _TEXT public align=16 class=CODE use16
global __U4D, __U4M

; Open Watcom C/16 compiler-helper ABI, independent 386 implementation.
; Inputs: DX:AX and CX:BX. SI, DI, BP, segment registers and SP are preserved.
; These are register helpers, not cdecl functions. No DOS/CRT dependency.

__U4M:
    movzx eax, ax
    movzx edx, dx
    shl edx, 16
    or eax, edx
    movzx ebx, bx
    movzx ecx, cx
    shl ecx, 16
    or ecx, ebx
    imul eax, ecx                 ; low 32 product bits, unsigned modulo 2^32
    mov edx, eax
    shr edx, 16                   ; DX:AX product; CX/BX are volatile
    ret

__U4D:
    movzx eax, ax
    movzx edx, dx
    shl edx, 16
    or eax, edx
    movzx ebx, bx
    movzx ecx, cx
    shl ecx, 16
    or ecx, ebx
    xor edx, edx
    div ecx                      ; caller must exclude zero, as for C division
    mov ebx, edx
    mov ecx, edx
    shr ecx, 16                   ; CX:BX remainder
    mov edx, eax
    shr edx, 16                   ; DX:AX quotient
    ret
