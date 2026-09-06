/* sw/common/uart.c — TX-only diagnostic UART driver.
 *
 * SYS-11: "READY=1 when one-byte holding slot empty; TX_DATA when not ready
 * returns SLVERR (not silently dropped)." Per SYS-07 a CSR SLVERR to a CPU
 * request is FATAL (permanent local CPU reset), so uart_putc must always
 * poll READY before writing TX_DATA — there is no software-visible recovery
 * from getting this wrong.
 */
#include "uart.h"
#include "regmap.h"
#include "mmio.h"

static void uart_wait_ready(void) {
    while ((mmio_read32(UART_STATUS_ADDR) & UART_STATUS_READY_MASK) == 0) {
        /* spin: diagnostic UART only, no RX/backpressure signal to wait on
         * besides polling STATUS.READY (SYS-11). */
    }
}

void uart_putc(char c) {
    uart_wait_ready();
    mmio_write32(UART_TX_DATA_ADDR, (uint32_t)(unsigned char)c);
}

void uart_puts(const char *s) {
    while (*s) {
        if (*s == '\n') {
            uart_putc('\r');
        }
        uart_putc(*s++);
    }
}

void uart_write_line(const char *s) {
    uart_puts(s);
    uart_putc('\r');
    uart_putc('\n');
}

static char hex_nibble(uint32_t v) {
    v &= 0xFu;
    return (char)(v < 10 ? ('0' + v) : ('a' + (v - 10)));
}

void uart_write_hex32(uint32_t v) {
    char buf[10];
    buf[0] = '0';
    buf[1] = 'x';
    for (int i = 0; i < 8; i++) {
        buf[2 + i] = hex_nibble(v >> (28 - 4 * i));
    }
    for (size_t i = 0; i < sizeof(buf); i++) {
        uart_putc(buf[i]);
    }
}
