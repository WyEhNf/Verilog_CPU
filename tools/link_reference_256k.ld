OUTPUT_ARCH(riscv)
ENTRY(_start)

/*
 * Differential-only layout for the public RISC-V-CPU-Simulator, whose Mem
 * API is fixed at 256 KiB.  Production images continue to use link.ld and a
 * 1 MiB stack top.
 */
MEMORY {
    rom (rx) : ORIGIN = 0x00000000, LENGTH = 0x00001000
    ram (rwx): ORIGIN = 0x00001000, LENGTH = 0x0003F000
}

SECTIONS {
    . = ORIGIN(rom);
    .text.startup : ALIGN(4) { KEEP(*(.text.startup)) } > rom
    ASSERT(SIZEOF(.text.startup) <= LENGTH(rom), "startup exceeds ROM")
    . = ORIGIN(ram);
    .text : ALIGN(4) { *(.text .text.*) } > ram
    .rodata : ALIGN(4) { *(.rodata .rodata.*) } > ram
    .data : ALIGN(4) { *(.data .data.*) } > ram
    .bss (NOLOAD) : ALIGN(4) {
        __bss_start = .;
        *(.bss .bss.* COMMON)
        . = ALIGN(4);
        __bss_end = .;
    } > ram
    __stack_top = ORIGIN(ram) + LENGTH(ram);
    _end = .;
    ASSERT(__stack_top == 0x00040000, "reference stack top must be 256 KiB")
    ASSERT(_end <= __stack_top, "reference image exceeds 256 KiB")
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.riscv.attributes) *(.debug*) }
}
