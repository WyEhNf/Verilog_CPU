void *memset(void *dst, int value, unsigned int count)
{
    unsigned char *out = (unsigned char *)dst;
    while (count != 0u) { *out++ = (unsigned char)value; --count; }
    return dst;
}

void *memcpy(void *dst, const void *src, unsigned int count)
{
    unsigned char *out = (unsigned char *)dst;
    const unsigned char *in = (const unsigned char *)src;
    while (count != 0u) { *out++ = *in++; --count; }
    return dst;
}

/*
 * The CPU-2026 rsort source uses legacy __sync intrinsics to make the same
 * source usable by threaded benchmark harnesses.  The selected workload is
 * strictly single-threaded, so RV32IM builds (without the A extension) can
 * implement the required operations as ordinary read/modify/write helpers.
 */
unsigned int __sync_fetch_and_add_4(volatile void *address, unsigned int value)
{
    volatile unsigned int *word = (volatile unsigned int *)address;
    unsigned int old = *word;
    *word = old + value;
    return old;
}

unsigned int __sync_add_and_fetch_4(volatile void *address, unsigned int value)
{
    volatile unsigned int *word = (volatile unsigned int *)address;
    unsigned int result = *word + value;
    *word = result;
    return result;
}
