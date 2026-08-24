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
