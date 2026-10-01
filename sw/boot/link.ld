/* Boot ROM: code and constants only (the ROM is read-only, no .data/.bss). */
OUTPUT_ARCH(riscv)
ENTRY(_start)

MEMORY
{
    ROM (rx) : ORIGIN = 0x00100000, LENGTH = 4K
}

SECTIONS
{
    .text : {
        KEEP(*(.text.start))
        *(.text .text.*)
        *(.rodata .rodata.* .srodata .srodata.*)
    } > ROM

    .data : { *(.data .data.* .sdata .sdata.*) } > ROM
    .bss  : { *(.bss .bss.* .sbss .sbss.* COMMON) } > ROM
    ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "boot ROM code must not use static variables")
}
