// Exercise the final legal word in the 256 MiB external RAM address range.
// A 1 MiB-configured bridge/model cannot pass this test.
int main(void)
{
    volatile unsigned int *const last_word =
        (volatile unsigned int *)0x0ffffffcu;
    // These lines map to the same hashed set as the final RAM line in the
    // tested 1024-line, two-way cache. Reading both forces a dirty eviction.
    *last_word = 0x13579bdfu;
    unsigned int first = *last_word;
    volatile unsigned int *const conflict_one =
        (volatile unsigned int *)(0x00002010u + ((first ^ 0x13579bdfu) & 12u));
    unsigned int second = *conflict_one;
    volatile unsigned int *const conflict_two =
        (volatile unsigned int *)(0x00004020u + (second & 12u));
    unsigned int third = *conflict_two;
    volatile unsigned int *const revisit =
        (volatile unsigned int *)(0x0ffffffcu - (third & 12u));
    unsigned int fourth = *revisit;
    unsigned int mismatch = (first ^ 0x13579bdfu) | second | third |
                            (fourth ^ 0x13579bdfu);
    return (mismatch == 0u) ? 0x256 : 0xBAD;
}
