; =============================================================================
; MAZFALL_ZOMBIE_ALPHA_v0.5 — engine kernel in pure x86_64 assembly
; -----------------------------------------------------------------------------
; NASM · Linux · no libc · raw syscalls · SSE2 math · ANSI terminal
; The engine soul — ASCII raycaster — preserved in pure machine code.
; Zombies/overheat/chaingun live in the C/Python versions; this is the kernel.
;
;   build:  nasm -f elf64 Mazfall_Zombie_Alpha_v0.5.asm -o mz.o
;           ld mz.o -o mz_asm
;   run:    ./mz_asm      (80x24+ vt100/xterm)
;   keys:   W/S forward·back · A/D strafe · J/L turn · Q/ESC quit
; =============================================================================

BITS 64
DEFAULT REL

%define SYS_read        0
%define SYS_write       1
%define SYS_ioctl       16
%define SYS_nanosleep   35
%define SYS_exit        60
%define SYS_fcntl       72
%define STDIN           0
%define STDOUT          1

%define TCGETS          0x5401
%define TCSETS          0x5402
%define F_SETFL         4
%define O_NONBLOCK      0x800
%define ICANON          0x02
%define ECHO            0x08

%define W               80
%define H               24
%define MW              16
%define MH              16

; =============================================================================
section .data
; 16x16 static map · 1=wall 0=floor · hand-carved
map:
    db 1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1
    db 1,0,0,0,0,0,0,0,1,0,0,0,0,0,0,1
    db 1,0,1,1,0,1,1,0,1,0,1,1,1,1,0,1
    db 1,0,1,0,0,0,1,0,0,0,0,0,0,1,0,1
    db 1,0,1,0,1,0,1,1,1,1,1,1,0,1,0,1
    db 1,0,0,0,1,0,0,0,0,0,0,1,0,0,0,1
    db 1,1,1,0,1,1,1,1,1,1,0,1,1,1,0,1
    db 1,0,0,0,0,0,0,0,0,1,0,0,0,0,0,1
    db 1,0,1,1,1,1,1,1,0,1,0,1,1,1,1,1
    db 1,0,1,0,0,0,0,1,0,1,0,0,0,0,0,1
    db 1,0,1,0,1,1,0,1,0,1,1,1,1,1,0,1
    db 1,0,0,0,1,0,0,0,0,0,0,0,0,1,0,1
    db 1,0,1,1,1,0,1,1,1,1,1,1,0,1,0,1
    db 1,0,0,0,0,0,0,0,0,0,0,1,0,0,0,1
    db 1,1,1,1,1,1,1,0,1,1,0,1,1,1,0,1
    db 1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1

ramp:       db " .:-=+*#%@"       ; Doomfall-0.1 soul, 10 chars
RAMP_LAST   equ 9

esc_init:   db 0x1b, "[2J", 0x1b, "[?25l", 0x1b, "[H"
esc_init_len equ $ - esc_init
esc_home:   db 0x1b, "[H"
esc_home_len equ $ - esc_home
esc_done:   db 0x1b, "[0m", 0x1b, "[?25h", 0x1b, "[2J", 0x1b, "[H"
esc_done_len equ $ - esc_done

f_half:     dq 0.5
f_one:      dq 1.0
f_step:     dq 0.05
f_offset:   dq 0.1
f_maxd:     dq 20.0
f_inv_maxd: dq 0.05
f_mv:       dq 0.18
f_tr:       dq 0.11
f_fov:      dq 1.0471975511965976
f_inv_w:    dq 0.0125
f_h:        dq 24.0
f_ramp_last: dq 9.0
f_start:    dq 1.5
f_zero:     dq 0.0

; =============================================================================
section .bss
player_x:   resq 1
player_y:   resq 1
player_a:   resq 1
saved_cos:  resq 1
saved_sin:  resq 1
saved_offset: resq 1
tmp_nx:     resq 1
tmp_ny:     resq 1
scrbuf:     resb (W+1)*H
old_tio:    resb 64
new_tio:    resb 64
ts:         resq 2
ikey:       resb 8

; =============================================================================
section .text
global _start

; -----------------------------------------------------------------------------
; write_all(rsi=buf, rdx=len)
; -----------------------------------------------------------------------------
write_all:
    mov     rax, SYS_write
    mov     rdi, STDOUT
    syscall
    ret

; -----------------------------------------------------------------------------
; cell_at(rdi=int_x, rsi=int_y) -> rax (1=wall/OOB, 0=floor)
; -----------------------------------------------------------------------------
cell_at:
    cmp     rdi, 0
    jl      .wall
    cmp     rdi, MW
    jge     .wall
    cmp     rsi, 0
    jl      .wall
    cmp     rsi, MH
    jge     .wall
    mov     rax, rsi
    imul    rax, rax, MW
    add     rax, rdi
    lea     rcx, [map]
    movzx   rax, byte [rcx + rax]
    ret
.wall:
    mov     rax, 1
    ret

; -----------------------------------------------------------------------------
; compute_sincos — x87 fsincos, input in xmm0, results to [saved_cos]/[saved_sin]
; -----------------------------------------------------------------------------
compute_sincos:
    sub     rsp, 16
    movsd   [rsp], xmm0
    fld     qword [rsp]
    fsincos                         ; ST0=cos, ST1=sin
    fstp    qword [saved_cos]
    fstp    qword [saved_sin]
    add     rsp, 16
    ret

; -----------------------------------------------------------------------------
; cast_ray(xmm0=px, xmm1=py, xmm2=angle) -> xmm0 = distance
; -----------------------------------------------------------------------------
cast_ray:
    movapd  xmm6, xmm0              ; xmm6 = px
    movapd  xmm7, xmm1              ; xmm7 = py
    movapd  xmm0, xmm2
    call    compute_sincos
    movsd   xmm3, [saved_cos]
    movsd   xmm4, [saved_sin]
    movsd   xmm5, [f_step]          ; t
.loop:
    movsd   xmm0, [f_maxd]
    ucomisd xmm5, xmm0
    jae     .return_maxd

    ; hx = px + cos*t
    movapd  xmm0, xmm3
    mulsd   xmm0, xmm5
    addsd   xmm0, xmm6
    cvttsd2si rdi, xmm0
    ; hy = py + sin*t
    movapd  xmm0, xmm4
    mulsd   xmm0, xmm5
    addsd   xmm0, xmm7
    cvttsd2si rsi, xmm0

    call    cell_at
    test    rax, rax
    jnz     .hit

    addsd   xmm5, [f_step]
    jmp     .loop
.hit:
    movapd  xmm0, xmm5
    ret
.return_maxd:
    movsd   xmm0, [f_maxd]
    ret

; =============================================================================
_start:
    ; init player
    mov     rax, [f_start]
    mov     [player_x], rax
    mov     [player_y], rax
    mov     rax, [f_zero]
    mov     [player_a], rax

    ; termios raw
    mov     rax, SYS_ioctl
    mov     rdi, STDIN
    mov     rsi, TCGETS
    lea     rdx, [old_tio]
    syscall

    mov     rcx, 8
    lea     rsi, [old_tio]
    lea     rdi, [new_tio]
    rep     movsq

    mov     eax, [new_tio + 12]
    and     eax, ~(ICANON | ECHO)
    mov     [new_tio + 12], eax
    mov     byte [new_tio + 17 + 6], 0
    mov     byte [new_tio + 17 + 5], 0

    mov     rax, SYS_ioctl
    mov     rdi, STDIN
    mov     rsi, TCSETS
    lea     rdx, [new_tio]
    syscall

    mov     rax, SYS_fcntl
    mov     rdi, STDIN
    mov     rsi, F_SETFL
    mov     rdx, O_NONBLOCK
    syscall

    lea     rsi, [esc_init]
    mov     rdx, esc_init_len
    call    write_all

; =============================================================================
main_loop:
    xor     r12, r12                ; x column
.col_loop:
    ; ra offset = ((x+0.5)/W - 0.5) * fov
    cvtsi2sd xmm0, r12
    addsd   xmm0, [f_half]
    mulsd   xmm0, [f_inv_w]
    subsd   xmm0, [f_half]
    mulsd   xmm0, [f_fov]
    movsd   [saved_offset], xmm0

    ; ra = player_a + offset
    addsd   xmm0, [player_a]
    movapd  xmm2, xmm0
    movsd   xmm0, [player_x]
    movsd   xmm1, [player_y]
    call    cast_ray                ; xmm0 = dist

    ; fisheye: d *= cos(offset)
    sub     rsp, 16
    movsd   [rsp], xmm0
    movsd   xmm0, [saved_offset]
    call    compute_sincos
    movsd   xmm1, [saved_cos]
    movsd   xmm0, [rsp]
    add     rsp, 16
    mulsd   xmm0, xmm1              ; xmm0 = corrected dist

    ; wh = H / (d+0.1)
    movapd  xmm1, xmm0
    addsd   xmm1, [f_offset]
    movsd   xmm2, [f_h]
    divsd   xmm2, xmm1
    cvttsd2si r14, xmm2
    cmp     r14, 0
    jge     .wh_ok
    xor     r14, r14
.wh_ok:
    cmp     r14, H
    jle     .wh_ok2
    mov     r14, H
.wh_ok2:

    ; shade = int((1 - d/maxd) * 9)
    movapd  xmm1, xmm0
    mulsd   xmm1, [f_inv_maxd]
    movsd   xmm2, [f_one]
    subsd   xmm2, xmm1
    mulsd   xmm2, [f_ramp_last]
    cvttsd2si r13, xmm2
    cmp     r13, 0
    jge     .sh_ok
    xor     r13, r13
.sh_ok:
    cmp     r13, RAMP_LAST
    jle     .sh_ok2
    mov     r13, RAMP_LAST
.sh_ok2:

    ; top = (H - wh)/2
    mov     r15, H
    sub     r15, r14
    sar     r15, 1
    cmp     r15, 0
    jge     .top_ok
    xor     r15, r15
.top_ok:

    ; bot = top + wh
    mov     rbx, r15
    add     rbx, r14
    cmp     rbx, H
    jle     .bot_ok
    mov     rbx, H
.bot_ok:

    ; fill column
    lea     rdi, [scrbuf]
    xor     r8, r8
.row_loop:
    cmp     r8, H
    jge     .row_done
    mov     rax, r8
    imul    rax, rax, (W+1)
    add     rax, r12

    cmp     r8, r15
    jl      .ceil
    cmp     r8, rbx
    jl      .wall_ch
    mov     sil, '.'
    jmp     .put
.ceil:
    mov     sil, ' '
    jmp     .put
.wall_ch:
    lea     r9, [ramp]
    mov     sil, [r9 + r13]
.put:
    mov     [rdi + rax], sil
    inc     r8
    jmp     .row_loop
.row_done:

    inc     r12
    cmp     r12, W
    jl      .col_loop

    ; add newlines
    lea     rdi, [scrbuf]
    xor     r8, r8
.nl_loop:
    cmp     r8, H
    jge     .nl_done
    mov     rax, r8
    imul    rax, rax, (W+1)
    add     rax, W
    mov     byte [rdi + rax], 10
    inc     r8
    jmp     .nl_loop
.nl_done:

    ; flush
    lea     rsi, [esc_home]
    mov     rdx, esc_home_len
    call    write_all
    lea     rsi, [scrbuf]
    mov     rdx, (W+1)*H
    call    write_all

    ; input
    mov     rax, SYS_read
    mov     rdi, STDIN
    lea     rsi, [ikey]
    mov     rdx, 1
    syscall
    test    rax, rax
    jle     .frame_end

    movzx   eax, byte [ikey]
    cmp     al, 27
    je      do_quit
    cmp     al, 'q'
    je      do_quit
    cmp     al, 'Q'
    je      do_quit

    cmp     al, 'w'
    je      .fwd
    cmp     al, 'W'
    je      .fwd
    cmp     al, 's'
    je      .back
    cmp     al, 'S'
    je      .back
    cmp     al, 'a'
    je      .strafe_l
    cmp     al, 'A'
    je      .strafe_l
    cmp     al, 'd'
    je      .strafe_r
    cmp     al, 'D'
    je      .strafe_r
    cmp     al, 'j'
    je      .turn_l
    cmp     al, 'J'
    je      .turn_l
    cmp     al, 'l'
    je      .turn_r
    cmp     al, 'L'
    je      .turn_r
    jmp     .frame_end

.fwd:
    movsd   xmm0, [player_a]
    call    compute_sincos
    movsd   xmm0, [saved_cos]
    mulsd   xmm0, [f_mv]
    addsd   xmm0, [player_x]
    movsd   [tmp_nx], xmm0
    movsd   xmm0, [saved_sin]
    mulsd   xmm0, [f_mv]
    addsd   xmm0, [player_y]
    movsd   [tmp_ny], xmm0
    call    try_move
    jmp     .frame_end

.back:
    movsd   xmm0, [player_a]
    call    compute_sincos
    movsd   xmm0, [saved_cos]
    mulsd   xmm0, [f_mv]
    movsd   xmm1, [player_x]
    subsd   xmm1, xmm0
    movsd   [tmp_nx], xmm1
    movsd   xmm0, [saved_sin]
    mulsd   xmm0, [f_mv]
    movsd   xmm1, [player_y]
    subsd   xmm1, xmm0
    movsd   [tmp_ny], xmm1
    call    try_move
    jmp     .frame_end

.strafe_l:
    movsd   xmm0, [player_a]
    call    compute_sincos
    movsd   xmm0, [saved_sin]
    mulsd   xmm0, [f_mv]
    addsd   xmm0, [player_x]
    movsd   [tmp_nx], xmm0
    movsd   xmm0, [saved_cos]
    mulsd   xmm0, [f_mv]
    movsd   xmm1, [player_y]
    subsd   xmm1, xmm0
    movsd   [tmp_ny], xmm1
    call    try_move
    jmp     .frame_end

.strafe_r:
    movsd   xmm0, [player_a]
    call    compute_sincos
    movsd   xmm0, [saved_sin]
    mulsd   xmm0, [f_mv]
    movsd   xmm1, [player_x]
    subsd   xmm1, xmm0
    movsd   [tmp_nx], xmm1
    movsd   xmm0, [saved_cos]
    mulsd   xmm0, [f_mv]
    addsd   xmm0, [player_y]
    movsd   [tmp_ny], xmm0
    call    try_move
    jmp     .frame_end

.turn_l:
    movsd   xmm0, [player_a]
    subsd   xmm0, [f_tr]
    movsd   [player_a], xmm0
    jmp     .frame_end

.turn_r:
    movsd   xmm0, [player_a]
    addsd   xmm0, [f_tr]
    movsd   [player_a], xmm0
    jmp     .frame_end

.frame_end:
    mov     qword [ts], 0
    mov     qword [ts+8], 50000000
    mov     rax, SYS_nanosleep
    lea     rdi, [ts]
    xor     rsi, rsi
    syscall
    jmp     main_loop

try_move:
    movsd   xmm0, [tmp_nx]
    cvttsd2si rdi, xmm0
    movsd   xmm0, [player_y]
    cvttsd2si rsi, xmm0
    call    cell_at
    test    rax, rax
    jnz     .skip_x
    mov     rax, [tmp_nx]
    mov     [player_x], rax
.skip_x:
    movsd   xmm0, [player_x]
    cvttsd2si rdi, xmm0
    movsd   xmm0, [tmp_ny]
    cvttsd2si rsi, xmm0
    call    cell_at
    test    rax, rax
    jnz     .skip_y
    mov     rax, [tmp_ny]
    mov     [player_y], rax
.skip_y:
    ret

do_quit:
    mov     rax, SYS_ioctl
    mov     rdi, STDIN
    mov     rsi, TCSETS
    lea     rdx, [old_tio]
    syscall
    lea     rsi, [esc_done]
    mov     rdx, esc_done_len
    call    write_all
    mov     rax, SYS_exit
    xor     rdi, rdi
    syscall

; .- ∞ recurse
