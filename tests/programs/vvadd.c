/* Scalar loop derived from ucb-bar/riscv-benchmarks vvadd/vvadd_main.c. */
static volatile int input_a[8] = {1, 2, 3, 4, 5, 6, 7, 8};
static volatile int input_b[8] = {8, 7, 6, 5, 4, 3, 2, 1};
static volatile int output[8];

int main(void)
{
    int checksum = 0;
    int index;
    for (index = 0; index < 8; ++index) {
        output[index] = input_a[index] + input_b[index];
        checksum += output[index];
    }
    return checksum;
}
