bits 16
cpu 386
; Linked last; the linker orders CONST/CONST2 before _DATA and omits _BSS.
segment _DATA public align=2 class=DATA use16
global rb_file_end
%ifdef RB_HDD_FIXTURE
    ; Exercise multiple FAT clusters while keeping BSS after the loaded file.
    times 4096 db 0xA5
%endif
rb_file_end:
segment _BSS public align=2 class=BSS use16
global rb_bss_end
rb_bss_end:
