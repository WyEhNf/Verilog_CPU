int main(void)
{
    volatile int upper = 100;
    int sum = 0;
    int value;
    for (value = 0; value <= upper; ++value)
        sum += value;
    return sum;
}
