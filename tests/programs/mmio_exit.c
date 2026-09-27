// Final-protocol smoke: the historical sentinel word is a legal ADDI and
// must not halt execution before the 32-bit MMIO exit store.
int main(void)
{
    __asm__ volatile (".word 0x0ff00513" ::: "a0");
    return 0x12345678;
}
