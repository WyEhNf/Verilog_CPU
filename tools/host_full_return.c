// Build test program sources with -Dmain=cpu_main, then link this wrapper
// without that macro to observe the full signed return value (not only the
// 8-bit host process exit status used by the old simulator manifest).
#include <stdio.h>

extern int cpu_main(void);

int main(void) {
    printf("%d\n", cpu_main());
    return 0;
}
