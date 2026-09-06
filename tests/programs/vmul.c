/* Scalar loop derived from ucb-bar/riscv-benchmarks multiply/multiply_main.c. */
static volatile int input_a[8] = {3, -4, 5, -6, 7, -8, 9, -10};
static volatile int input_b[8] = {11, 12, -13, -14, 15, 16, -17, -18};
static volatile int output[8];

int main(void)
{
    int checksum = 0;
    int index;
    for (index = 0; index < 8; ++index) {
        output[index] = input_a[index] * input_b[index];
        checksum += output[index];
    }
    return checksum;
}
