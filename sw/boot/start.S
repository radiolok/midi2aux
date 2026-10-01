/* Boot ROM entry points (reset vector = BOOTROM_BASE):
 *   +0  normal reset: wait for a UART image, then boot from SPI flash
 *   +4  loader requested by the firmware (magic already received): load from UART now
 * No .data/.bss: the stack sits at the top of RAM (SYSINFO_RAM_BYTES), images load at 0. */
    .section .text.start, "ax"
    .global _start
    .option push
    .option norvc               /* 4-byte jumps: the entry table offsets are fixed */
_start:
    j       1f
    j       2f
    .option pop
1:  li      a0, 0
    j       3f
2:  li      a0, 1
3:  li      t0, 0x10000410      /* SYSINFO_RAM_BYTES */
    lw      sp, 0(t0)
    call    boot_main
4:  j       4b
