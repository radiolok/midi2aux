/* Firmware entry at RAM 0: gp, sp, clear .bss, main(). */
    .section .text.start, "ax"
    .global _start
_start:
    .option push
    .option norelax
    la      gp, __global_pointer$
    la      sp, __stack_top     /* no gp-relative relaxation: near the end of RAM it can overflow */
    la      a0, __bss_start
    la      a1, __bss_end
    .option pop
1:  bgeu    a0, a1, 2f
    sw      zero, 0(a0)
    addi    a0, a0, 4
    j       1b
2:  call    main
3:  j       3b
