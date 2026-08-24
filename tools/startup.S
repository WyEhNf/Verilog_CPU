    .option norelax
    .section .text.startup, "ax", @progbits
    .align 2
    .globl _start
    .type _start, @function
_start:
    lui     sp, %hi(__stack_top)
    addi    sp, sp, %lo(__stack_top)
    lui     t0, %hi(__bss_start)
    addi    t0, t0, %lo(__bss_start)
    lui     t1, %hi(__bss_end)
    addi    t1, t1, %lo(__bss_end)
.Lbss:
    beq     t0, t1, .Lmain
    sw      zero, 0(t0)
    addi    t0, t0, 4
    jal     zero, .Lbss
.Lmain:
    jal     ra, main
    .word   0x0ff00513
.Lhalt_loop:
    jal     zero, .Lhalt_loop
    .size _start, .-_start
