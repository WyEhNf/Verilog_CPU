/* Exercise naturally aligned RV32IM LH/LHU/SH through the full CPU. */
static int read_signed_half(volatile signed short *address)
{
    int value;
    __asm__ volatile ("lh %0, 0(%1)" : "=r" (value) : "r" (address) : "memory");
    return value;
}

int main(void)
{
    volatile unsigned short pair[4] = {0x1234u, 0x8001u, 0x55aau, 0x77ccu};
    volatile signed short *signed_pair = (volatile signed short *)pair;

    if (read_signed_half(&signed_pair[0]) != 0x1234 ||
        read_signed_half(&signed_pair[1]) != -32767)
        return 101;
    if (pair[1] != 0x8001u || pair[2] != 0x55aau)
        return 102;

    /* Two halfword stores into one word test byte masks and ordering. */
    pair[0] = 0x80feu;
    pair[1] = 0x3456u;
    if (read_signed_half(&signed_pair[0]) != -32514 || pair[0] != 0x80feu)
        return 103;
    if (read_signed_half(&signed_pair[1]) != 0x3456 || pair[1] != 0x3456u)
        return 104;
    if (pair[2] != 0x55aau || pair[3] != 0x77ccu)
        return 105;
    return 0;
}
