; Read-only, bounded FAT16 loader for the owned RetroBoot volume.
bits 16
cpu 386
org 0x2000
%include "include/boot.inc"
    jmp short entry
    db 'RBB1'
    dw 0                       ; padded file bytes, patched by host builder
    dw 0                       ; checksum: sum of all file words = 0
    times RB_HEADER - ($ - $$) db 0
entry:
    cld
    xor ax, ax
    mov ds, ax
    mov es, ax
    push ds
    push es
    int 0x12
    pop es
    pop ds
    cmp ax, 128                 ; stage2 and stack end at physical 20000h
    jb memory_error
    mov ax, [0x040E]            ; EBDA segment, zero means absent
    test ax, ax
    jz .memory_ok
    cmp ax, 0x2000
    jb memory_error
.memory_ok:
    ; This version accepts the project's FAT16 format, not arbitrary FAT BPBs.
    cmp word [RB_VBR + 11], 512
    jne bpb_error
    cmp word [RB_VBR + 14], 1
    jne bpb_error
    cmp byte [RB_VBR + 16], 2
    jne bpb_error
    cmp word [RB_VBR + 17], 512
    jne bpb_error
    cmp word [RB_VBR + 19], 0
    jne bpb_error
    movzx ecx, byte [RB_VBR + 13]
    test ecx, ecx
    jz bpb_error
    cmp ecx, 64
    ja bpb_error
    lea eax, [ecx - 1]
    test eax, ecx
    jnz bpb_error
    mov [cluster_sectors], ecx
    mov eax, [RB_VBR + 28]
    cmp eax, [RB_MBR + 436]
    jne bpb_error
    mov edx, eax
    add edx, [RB_VBR + 32]
    jc bpb_error
    cmp edx, eax
    jbe bpb_error
    cmp dword [RB_CAPACITY + 4], 0
    jne .capacity_ok
    cmp edx, [RB_CAPACITY]
    ja bpb_error
.capacity_ok:
    inc eax
    mov [fat_lba], eax
    movzx ebx, word [RB_VBR + 22]
    test ebx, ebx
    jz bpb_error
    mov [fat_sectors], ebx
    add eax, ebx
    jc bpb_error
    add eax, ebx
    jc bpb_error
    mov [root_lba], eax
    add eax, 32
    jc bpb_error
    cmp eax, edx
    jae bpb_error
    mov [data_lba], eax
    cmp [RB_VBR + 66], eax      ; contiguous bootstrap must lie in data area
    jb bpb_error
    sub edx, eax
    mov eax, edx
    xor edx, edx
    div ecx
    cmp eax, 4085
    jb bpb_error
    cmp eax, 65525
    jae bpb_error
    inc eax
    mov [last_cluster], ax
    inc eax
    shl ebx, 8                 ; 256 FAT16 entries per sector
    cmp ebx, eax
    jb bpb_error

    mov eax, [root_lba]
    mov cx, 32
.root_sector:
    mov bx, RB_BUFFER
    call read_sector
    jc io_error
    mov di, RB_BUFFER
    mov dx, 16
.root_entry:
    cmp byte [di], 0
    je missing_error
    cmp byte [di], 0xE5
    je .next_entry
    test byte [di + 11], 0x18   ; skip directories, volume labels and LFNs
    jnz .next_entry
    push cx
    push di
    mov si, filename
    mov cx, 11
    cld
    repe cmpsb
    pop di
    pop cx
    je .found
.next_entry:
    add di, 32
    dec dx
    jnz .root_entry
    inc eax
    loop .root_sector
    jmp missing_error
.found:
    cmp word [di + 20], 0       ; no FAT32 high cluster word in this format
    jne file_error
    mov ax, [di + 26]
    mov [cluster], ax
    mov eax, [di + 28]
    cmp eax, RB_HEADER + 1
    jb file_error
    cmp eax, RB_STAGE2_MAX
    ja file_error
    mov [file_bytes], eax
    add eax, 511
    shr eax, 9
    mov [remaining], ax        ; at most 96 sector reads, even with a FAT loop
    mov word [destination], 0
.cluster:
    movzx eax, word [cluster]
    cmp ax, 2
    jb fat_error
    cmp ax, [last_cluster]
    ja fat_error
    cmp ax, 0xFFF0
    jae fat_error
    sub eax, 2
    mul dword [cluster_sectors]
    add eax, [data_lba]
    mov cx, [cluster_sectors]
.sector:
    mov bx, [destination]
    mov dx, RB_STAGE2_SEG
    mov es, dx
    call read_sector
    jc io_error
    add word [destination], 512
    inc eax
    dec word [remaining]
    jz .chain
    loop .sector
.chain:
    ; Read both copies of the current FAT entry. No silent copy selection.
    xor dx, dx
    mov es, dx
    movzx eax, word [cluster]
    shl eax, 1
    mov si, ax
    and si, 511
    shr eax, 9
    add eax, [fat_lba]
    mov bx, RB_BUFFER
    call read_sector
    jc io_error
    mov dx, [RB_BUFFER + si]
    add eax, [fat_sectors]
    call read_sector
    jc io_error
    cmp dx, [RB_BUFFER + si]
    jne copies_error
    cmp word [remaining], 0
    je .end_chain
    mov [cluster], dx
    jmp .cluster               ; validates EOC, free, reserved, bad, range
.end_chain:
    cmp dx, 0xFFF8             ; exact length: reject overlong/cyclic chains
    jb fat_error

    mov ax, RB_STAGE2_SEG
    mov es, ax
    cmp word [es:0], 0x1EEB
    jne header_error
    cmp dword [es:2], 'RBS2'
    jne header_error
    cmp word [es:6], RB_HEADER
    jne header_error
    mov eax, [file_bytes]
    cmp [es:8], eax
    jne header_error
    cmp word [es:16], RB_STAGE2_SEG
    jne header_error
    cmp word [es:18], RB_HEADER
    jne header_error
    cmp word [es:20], 2
    jne header_error
    cmp [es:22], ax             ; BSS starts at or after the exact file end
    jb header_error
    mov dx, [es:24]
    cmp dx, [es:22]
    jbe header_error
    cmp dx, RB_STACK_LOW
    ja header_error
    cmp word [es:26], RB_STACK_LOW
    jne header_error
    cmp word [es:28], RB_STACK_TOP
    jne header_error
    cmp word [es:30], 0
    jne header_error
    mov ecx, eax
    sub ecx, RB_HEADER
    mov si, RB_HEADER
    mov edx, 0xFFFFFFFF
.crc_byte:
    mov al, [es:si]
    xor dl, al
    mov bl, 8
.crc_bit:
    shr edx, 1
    jnc .next_bit
    xor edx, 0xEDB88320
.next_bit:
    dec bl
    jnz .crc_bit
    inc si
    dec ecx
    jnz .crc_byte
    not edx
    cmp edx, [es:12]
    jne crc_error
%ifdef RB_TEST
    ; Poison only the now-validated BSS, after the last partial sector load.
    ; This proves that startup clears it, independent of initial guest RAM.
    mov di, [es:22]
    mov cx, [es:24]
    sub cx, di
    mov al, 0xA5
    cld
    rep stosb
%endif
    mov dl, [RB_DRIVE]
    jmp RB_STAGE2_SEG:RB_HEADER

memory_error: mov si, memory_message
    jmp fatal
bpb_error: mov si, bpb_message
    jmp fatal
missing_error: mov si, missing_message
    jmp fatal
file_error: mov si, file_message
    jmp fatal
fat_error: mov si, fat_message
    jmp fatal
copies_error: mov si, copies_message
    jmp fatal
io_error: mov si, io_message
    jmp fatal
header_error: mov si, header_message
    jmp fatal
crc_error: mov si, crc_message
    jmp fatal

%include "boot/disk.inc"
%include "boot/fatal.inc"
filename: db 'RBSTG2  BIN'
memory_message: db 'RB MEMORY ERROR', 13, 10, 0
bpb_message: db 'RB BPB ERROR', 13, 10, 0
missing_message: db 'RB FILE MISSING', 13, 10, 0
file_message: db 'RB FILE SIZE ERROR', 13, 10, 0
fat_message: db 'RB FAT CHAIN ERROR', 13, 10, 0
copies_message: db 'RB FAT COPIES ERROR', 13, 10, 0
io_message: db 'RB READ ERROR', 13, 10, 0
header_message: db 'RB HEADER ERROR', 13, 10, 0
crc_message: db 'RB CRC ERROR', 13, 10, 0
align 4
fat_lba: dd 0
fat_sectors: dd 0
root_lba: dd 0
data_lba: dd 0
cluster_sectors: dd 0
file_bytes: dd 0
last_cluster: dw 0
cluster: dw 0
remaining: dw 0
destination: dw 0
    times (-($ - $$)) & 511 db 0
%if ($ - $$) > RB_BOOT_LIMIT * 512
    %error "Bootstrap exceeds its memory budget"
%endif
