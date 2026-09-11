/* CN-EXTMEM-01 v0.3, CNEM-05/06/17/20. Runtime host inputs only. */
#include <stdint.h>
#include <stddef.h>
extern void rvv_gemv_int8(const int8_t *, const int8_t *, int32_t *, size_t, size_t);
static uint32_t signature(const volatile int32_t *c, uint32_t n) {
    uint32_t sum = 0;
    for (uint32_t j = 0; j < n; ++j) sum += (uint32_t)c[j] * (j + 1u);
    return sum;
}
int main(void) {
    volatile uint32_t *const descriptor = (volatile uint32_t *)0x20018000;
    volatile uint32_t *const record = (volatile uint32_t *)0x20018100;
    const uint32_t salt = descriptor[0];
    const uint32_t run_id = descriptor[1];
    record[1] = 1;
    record[2] = run_id;
    /* Salt selects host-generated inputs, never baked-in arithmetic answers. */
    if (salt != 0 && salt != 17) { record[3] = 2; return 2; }
    rvv_gemv_int8((const int8_t *)0x20010000, (const int8_t *)0x20011000,
                  (int32_t *)0x20013000, 64, 64);
    rvv_gemv_int8((const int8_t *)0x20014000, (const int8_t *)0x20015000,
                  (int32_t *)0x20016000, 5, 33);
    record[4] = signature((const volatile int32_t *)0x20013000, 64);
    record[5] = signature((const volatile int32_t *)0x20016000, 33);
    record[6] = 2;
    *(volatile uint8_t *)0x20018201 = 0x5a;
    *(volatile uint16_t *)0x20018206 = 0x1234;
    *(volatile uint32_t *)0x2001820c = 0x89abcdef;
    uint32_t failure = (*(volatile uint8_t *)0x20018201 != 0x5a) |
        (*(volatile uint16_t *)0x20018206 != 0x1234) |
        (*(volatile uint32_t *)0x2001820c != 0x89abcdef);
    record[3] = failure;
    return (int)failure;
}
