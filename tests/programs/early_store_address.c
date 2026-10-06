#include <stdint.h>

static volatile uint32_t words[16] = {
    0, 0, 0, 0, 0x12345678, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0
};

// Long-latency store data, disjoint/alias loads, narrow stores, unresolved
// bases, same-bundle dependencies and a killed early-address store. Keep the
// exact instruction order visible rather than relying on compiler scheduling.
int main(void) {
    uint32_t result;
    __asm__ volatile(
        "li %0, 0\n"
        "li t0, 37\n"
        "li t1, 1\n"
        "div t2, t0, t1\n"
        "sw t2, 0(%1)\n"
        "lw t3, 16(%1)\n"
        "li t4, 0x12345678\n"
        "bne t3, t4, 1f\n"
        "lw t3, 0(%1)\n"
        "bne t3, t0, 2f\n"
        "li t0, 0x89abcdef\n"
        "divu t2, t0, t1\n"
        "sh t2, 6(%1)\n"
        "lhu t3, 6(%1)\n"
        "li t4, 0xcdef\n"
        "bne t3, t4, 3f\n"
        "divu t2, t0, t1\n"
        "sb t2, 9(%1)\n"
        "lbu t3, 9(%1)\n"
        "li t4, 0xef\n"
        "bne t3, t4, 3f\n"
        "divu t2, %1, t1\n"
        "li t0, 91\n"
        "sw t0, 0(t2)\n"
        "lw t3, 0(%1)\n"
        "bne t3, t0, 4f\n"
        "addi t2, %1, 32\n"
        "sw t0, 0(t2)\n"
        "lw t3, 32(%1)\n"
        "bne t3, t0, 5f\n"
        "div t2, t0, t1\n"
        "beq t1, t1, 7f\n"
        "sw t2, 16(%1)\n"
        "7:\n"
        "lw t3, 16(%1)\n"
        "li t4, 0x12345678\n"
        "bne t3, t4, 6f\n"
        "j 8f\n"
        "1: li %0, 1\n j 8f\n"
        "2: li %0, 2\n j 8f\n"
        "3: li %0, 3\n j 8f\n"
        "4: li %0, 4\n j 8f\n"
        "5: li %0, 5\n j 8f\n"
        "6: li %0, 6\n"
        "8:\n"
        : "=&r"(result)
        : "r"(words)
        : "t0", "t1", "t2", "t3", "t4", "memory"
    );
    return (int)result;
}
