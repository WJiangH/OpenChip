/* sw/common/uart.h — TX-only diagnostic UART driver (SYS-11, contract.json uart block). */
#ifndef OPENCHIP_SW_COMMON_UART_H
#define OPENCHIP_SW_COMMON_UART_H

#include <stddef.h>
#include <stdint.h>

/* Reset divisor is 16 (legal range 2..65535); we keep the reset divisor
 * rather than reprogram it — SYS-11: "Divisor writes while BUSY reject",
 * and there is no requirement to change the simulation baud rate. */
void uart_putc(char c);
void uart_puts(const char *s);
/* Appends "\n" after s; used for the one-line-per-stage requirement. */
void uart_write_line(const char *s);
void uart_write_hex32(uint32_t v);

#endif /* OPENCHIP_SW_COMMON_UART_H */
