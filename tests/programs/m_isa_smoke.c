static unsigned int do_mul(unsigned int a, unsigned int b)
{
    unsigned int result;
    __asm__ volatile ("mul %0, %1, %2" : "=r" (result) : "r" (a), "r" (b));
    return result;
}

static unsigned int do_mulh(unsigned int a, unsigned int b)
{
    unsigned int result;
    __asm__ volatile ("mulh %0, %1, %2" : "=r" (result) : "r" (a), "r" (b));
    return result;
}

static unsigned int do_mulhsu(unsigned int a, unsigned int b)
{
    unsigned int result;
    __asm__ volatile ("mulhsu %0, %1, %2" : "=r" (result) : "r" (a), "r" (b));
    return result;
}

static unsigned int do_mulhu(unsigned int a, unsigned int b)
{
    unsigned int result;
    __asm__ volatile ("mulhu %0, %1, %2" : "=r" (result) : "r" (a), "r" (b));
    return result;
}

static unsigned int do_div(unsigned int a, unsigned int b)
{
    unsigned int result;
    __asm__ volatile ("div %0, %1, %2" : "=r" (result) : "r" (a), "r" (b));
    return result;
}

static unsigned int do_divu(unsigned int a, unsigned int b)
{
    unsigned int result;
    __asm__ volatile ("divu %0, %1, %2" : "=r" (result) : "r" (a), "r" (b));
    return result;
}

static unsigned int do_rem(unsigned int a, unsigned int b)
{
    unsigned int result;
    __asm__ volatile ("rem %0, %1, %2" : "=r" (result) : "r" (a), "r" (b));
    return result;
}

static unsigned int do_remu(unsigned int a, unsigned int b)
{
    unsigned int result;
    __asm__ volatile ("remu %0, %1, %2" : "=r" (result) : "r" (a), "r" (b));
    return result;
}

int main(void)
{
    volatile unsigned int signed_a = 0xfffffff9u;
    volatile unsigned int signed_b = 3u;
    volatile unsigned int int_min = 0x80000000u;
    volatile unsigned int minus_one = 0xffffffffu;
    unsigned int failures = 0;

    failures += do_mul(signed_a, signed_b) != 0xffffffebu;
    failures += do_mulh(signed_a, signed_b) != 0xffffffffu;
    failures += do_mulhsu(signed_a, signed_b) != 0xffffffffu;
    failures += do_mulhu(signed_a, signed_b) != 0x00000002u;
    failures += do_div(signed_a, signed_b) != 0xfffffffeu;
    failures += do_divu(signed_a, signed_b) != 0x55555553u;
    failures += do_rem(signed_a, signed_b) != 0xffffffffu;
    failures += do_remu(signed_a, signed_b) != 0x00000000u;
    failures += do_div(signed_a, 0u) != 0xffffffffu;
    failures += do_divu(signed_a, 0u) != 0xffffffffu;
    failures += do_rem(signed_a, 0u) != signed_a;
    failures += do_remu(signed_a, 0u) != signed_a;
    failures += do_div(int_min, minus_one) != int_min;
    failures += do_rem(int_min, minus_one) != 0u;

    return failures == 0u ? 90 : (int)(0x80u | failures);
}
