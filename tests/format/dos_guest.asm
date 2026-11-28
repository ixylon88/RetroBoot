; A DOS .COM file for the T11 fixture. All file I/O uses DOS handles.
bits 16
cpu 386
org 100h

start:
    cld
    push ds
    pop es
    ; FreeDOS runs this as its shell with /BOOT. Without arguments the
    ; program returns to the original DOS command interpreter on completion.
    mov si, 81h
    xor cx, cx
    mov cl, [80h]
    jcxz .handler
.skip_spaces:
    lodsb
    cmp al, ' '
    loope .skip_spaces
    cmp al, '/'
    jne .handler
    cmp cx, 4
    jb .handler
    cmp dword [si], 'BOOT'
    jne .handler
    inc byte [as_shell]
.handler:
    mov ax, 2524h
    mov dx, critical_error
    int 21h
    mov dx, msg_title
    call line
    mov dx, msg_select
    call key
    cmp al, 27
    je cancel
    cmp al, '1'
    je .p1
    cmp al, '2'
    jne cancel
    inc byte [slot]
    inc byte [file_path]
    inc byte [id_path]
    inc byte [id_text + id_slot]
    mov dx, p2
    jmp .selected
.p1:
    mov dx, p1
.selected:
    call line
    call check_volume
    jc target_error
    mov dx, msg_write_menu
    call key
    and al, 0dfh
    cmp al, 'W'
    je write_new
    cmp al, 'V'
    jne cancel
    call verify_file
    jc file_error
    mov dx, read_pass
    call line
    mov dx, msg_delete_menu
    call key
    and al, 0dfh
    cmp al, 'D'
    jne cancel
    ; The medium and the file may have changed at the confirmation prompt.
    call check_volume
    jc target_error
    call verify_file
    jc file_error
    mov dx, file_path
    mov ah, 41h
    int 21h
    jc io_error
    mov dx, delete_pass
    jmp finish

write_new:
    call check_volume
    jc target_error
    xor cx, cx
    mov dx, file_path
    mov ah, 5bh                 ; create new, fails if the name already exists
    int 21h
    jc create_error
    mov [handle], ax
    mov byte [block], 0
.next:
    call pattern
    mov bx, [handle]
    mov dx, expected
    mov ah, 40h
    int 21h
    jc .failed
    cmp ax, cx
    jne .failed
    inc byte [block]
    cmp byte [block], full_blocks
    jbe .next
    mov bx, [handle]
    mov ah, 68h                 ; commit file buffers before reporting success
    int 21h
    jc .failed
    call close_file
    jc io_error
    mov dx, write_pass
    jmp finish
.failed:
    call close_file
    jmp io_error

; Check the serial of the DOS logical drive and a kit-specific file on that
; same drive. C: and D: are explicit. Other letters are never searched.
check_volume:
    xor bx, bx
    mov bl, [slot]
    add bl, 2                   ; DOS uses 1 = A:
    mov cx, 0866h               ; get media ID
    cmp bl, 3
    je .query
    mov cx, 4866h               ; FAT32 IOCTL category
.query:
    mov dx, media_id
    mov ax, 440dh
    int 21h
    jc .bad
    mov eax, serial_p1
    cmp byte [slot], 1
    je .serial
    mov eax, serial_p2
.serial:
    cmp eax, [media_id + 2]
    jne .bad
    mov dx, id_path
    mov ax, 3d00h
    int 21h
    jc .bad
    mov [handle], ax
    mov bx, ax
    mov dx, actual
    mov cx, id_length + 1       ; also rejects trailing bytes
    mov ah, 3fh
    int 21h
    jc .close_bad
    cmp ax, id_length
    jne .close_bad
    mov si, id_text
    mov di, actual
    mov cx, id_length
    repe cmpsb
    jne .close_bad
    jmp close_file
.close_bad:
    call close_file
.bad:
    stc
    ret

verify_file:
    mov dx, file_path
    mov ax, 3d00h
    int 21h
    jc .bad
    mov [handle], ax
    mov byte [block], 0
.next:
    call pattern
    mov bx, [handle]
    mov dx, actual
    mov ah, 3fh
    int 21h
    jc .close_bad
    cmp ax, cx
    jne .close_bad
    mov si, expected
    mov di, actual
    repe cmpsb
    jne .close_bad
    inc byte [block]
    cmp byte [block], full_blocks
    jbe .next
    mov cx, 1                   ; verify the exact end of file
    mov dx, actual
    mov ah, 3fh
    int 21h
    jc .close_bad
    test ax, ax
    jnz .close_bad
    jmp close_file
.close_bad:
    call close_file
.bad:
    stc
    ret

close_file:
    mov bx, [handle]
    mov ah, 3eh
    int 21h
    ret

; 96 complete 1-KiB blocks and a 17-byte tail. The pattern depends on the
; volume, block, quarter of the block and byte position.
full_blocks equ 96
pattern:
    mov cx, 1024
    cmp byte [block], full_blocks
    jne .fill
    mov cx, 17
.fill:
    mov di, expected
    xor bx, bx
.byte:
    mov al, bl
    xor al, bh
    add al, [block]
    add al, [slot]
    stosb
    inc bx
    cmp bx, cx
    jb .byte
    ret

critical_error:
    mov al, 3                   ; DOS "fail" for a missing or unreadable drive
    iret

; DOS console output plus the same bytes on the QEMU test console.
line:
    mov si, dx
.char:
    lodsb
    test al, al
    jz .done
    out 0e9h, al
    mov dl, al
    mov ah, 02h
    int 21h
    jmp .char
.done:
    ret
key:
    call line
    mov ah, 08h
    int 21h
    ret

target_error:
    mov dx, msg_target_bad
    jmp failure
create_error:
    mov dx, msg_create_bad
    jmp failure
file_error:
    mov dx, msg_file_bad
    jmp failure
io_error:
    mov dx, msg_io_bad
failure:
    call line
    mov dx, blocked
    mov byte [result], 1
    jmp finish
cancel:
    mov dx, ended
finish:
    call line
    cmp byte [as_shell], 0
    je .exit
    mov dx, msg_restart
    call line
.halt:
    sti
    hlt
    jmp .halt
.exit:
    mov al, [result]
    mov ah, 4ch
    int 21h

%include "dos_guest_text.inc"
p1 db 'P1  FAT16  C:', 13, 10, 0
p2 db 'P2  FAT32  D:', 13, 10, 0
write_pass db 'RB DOS WRITE PASS', 13, 10, 0
read_pass db 'RB DOS READ PASS', 13, 10, 0
delete_pass db 'RB DOS DELETE PASS', 13, 10, 0
blocked db 'RB DOS BLOCKED', 13, 10, 0
ended db 'RB DOS END', 13, 10, 0
file_path db 'C:', 92, 'RBT11.DAT', 0
id_path db 'C:', 92, 'RBT11.ID', 0
slot db 1
as_shell db 0
result db 0
block db 0
handle dw 0
media_id times 25 db 0
section .bss
expected resb 1024
actual resb 1024
